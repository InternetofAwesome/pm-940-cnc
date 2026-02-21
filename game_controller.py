#!/usr/bin/env python3
"""
Gamepad shim HAL component for LinuxCNC.

Reads an evdev-compatible game controller (e.g. 8Bitdo) and exposes
its inputs as HAL pins.  When the controller is not connected, all
outputs hold safe defaults (zero).  Reconnection is automatic.

Jog outputs (jog-x, jog-y, jog-z) combine stick position with the
right trigger as a speed multiplier — no trigger squeeze = no motion.

Usage in HAL:
    loadusr -W game_controller.py
    net jog-x-analog  gamepad_shim.jog-x
    net jog-y-analog  gamepad_shim.jog-y
    net jog-z-analog  gamepad_shim.jog-z
"""

import hal
import select
import sys
import time

from evdev import InputDevice, ecodes, list_devices

RECONNECT_INTERVAL = 1.0  # seconds between device scans


class GamepadShim:
    def __init__(self):
        self.h = hal.component("gamepad_shim")

        # Raw analog stick outputs (-1.0 … 1.0)
        self.h.newpin("lx", hal.HAL_FLOAT, hal.HAL_OUT)
        self.h.newpin("ly", hal.HAL_FLOAT, hal.HAL_OUT)
        self.h.newpin("rx", hal.HAL_FLOAT, hal.HAL_OUT)
        self.h.newpin("ry", hal.HAL_FLOAT, hal.HAL_OUT)

        # Trigger outputs (0.0 … 1.0)
        self.h.newpin("lt", hal.HAL_FLOAT, hal.HAL_OUT)
        self.h.newpin("rt", hal.HAL_FLOAT, hal.HAL_OUT)

        # Computed jog outputs: stick * right-trigger (-1.0 … 1.0)
        self.h.newpin("jog-x", hal.HAL_FLOAT, hal.HAL_OUT)
        self.h.newpin("jog-y", hal.HAL_FLOAT, hal.HAL_OUT)
        self.h.newpin("jog-z", hal.HAL_FLOAT, hal.HAL_OUT)

        # Connection status
        self.h.newpin("connected", hal.HAL_BIT, hal.HAL_OUT)

        # Buttons
        for name in ["a", "b", "x", "y", "lb", "rb",
                      "back", "start", "ls", "rs",
                      "up", "down", "left", "right"]:
            self.h.newpin(name, hal.HAL_BIT, hal.HAL_OUT)

        # Configurable parameters
        self.h.newparam("deadzone", hal.HAL_FLOAT, hal.HAL_RW)
        self.h.newparam("vendor", hal.HAL_S32, hal.HAL_RW)
        self.h.newparam("product", hal.HAL_S32, hal.HAL_RW)

        # Internal state for raw values (used to compute jog outputs)
        self._lx = 0.0
        self._ly = 0.0
        self._ry = 0.0
        self._rt = 0.0

        # Axis info cache: evdev code -> (min, max) from device caps
        self._axis_info = {}

        self.h["deadzone"] = 0.15
        self._reset()
        self.h.ready()

    # ------------------------------------------------------------------
    # Safe defaults
    # ------------------------------------------------------------------
    def _reset(self):
        """Zero every output pin and internal state."""
        self._lx = self._ly = self._ry = self._rt = 0.0
        for pin_name in list(self.h.getpins()):
            try:
                pin = self.h[pin_name]
                if isinstance(pin, float):
                    self.h[pin_name] = 0.0
                else:
                    self.h[pin_name] = 0
            except Exception:
                pass
        self.h["connected"] = False

    # ------------------------------------------------------------------
    # Device discovery
    # ------------------------------------------------------------------
    def _find_device(self):
        """Scan evdev devices; optionally filter by vendor/product."""
        vid = int(self.h["vendor"])
        pid = int(self.h["product"])

        for path in list_devices():
            try:
                dev = InputDevice(path)
                if vid and dev.info.vendor != vid:
                    continue
                if pid and dev.info.product != pid:
                    continue
                # Must have at least one absolute axis to be a gamepad
                caps = dev.capabilities(absinfo=True)
                if ecodes.EV_ABS not in caps:
                    continue
                # Cache axis ranges from device capabilities
                self._axis_info = {}
                for code, absinfo in caps[ecodes.EV_ABS]:
                    self._axis_info[code] = (absinfo.min, absinfo.max)
                return dev
            except Exception:
                continue
        return None

    # ------------------------------------------------------------------
    # Value scaling
    # ------------------------------------------------------------------
    def _scale_axis(self, code, raw):
        """Scale raw axis value to -1.0 … 1.0 using device-reported range."""
        info = self._axis_info.get(code)
        if not info:
            return 0.0
        lo, hi = info
        if hi == lo:
            return 0.0
        return 2.0 * (raw - lo) / (hi - lo) - 1.0

    def _scale_trigger(self, code, raw):
        """Scale raw trigger value to 0.0 … 1.0 using device-reported range."""
        info = self._axis_info.get(code)
        if not info:
            return 0.0
        lo, hi = info
        if hi == lo:
            return 0.0
        return (raw - lo) / (hi - lo)

    def _apply_deadzone(self, value):
        """Return 0.0 if within deadzone, otherwise rescale to full range."""
        dz = self.h["deadzone"]
        if abs(value) < dz:
            return 0.0
        # Rescale so the output ramps from 0 at the deadzone edge to ±1
        sign = 1.0 if value > 0 else -1.0
        return sign * (abs(value) - dz) / (1.0 - dz)

    # ------------------------------------------------------------------
    # Update computed jog pins
    # ------------------------------------------------------------------
    def _update_jog_outputs(self):
        """Combine stick values with right trigger for jog outputs."""
        rt = self._rt
        self.h["jog-x"] = self._apply_deadzone(self._lx) * rt
        self.h["jog-y"] = self._apply_deadzone(self._ly) * rt
        self.h["jog-z"] = self._apply_deadzone(self._ry) * rt

    # ------------------------------------------------------------------
    # Button mapping — evdev BTN codes to HAL pin names
    # ------------------------------------------------------------------
    BUTTON_MAP = {
        ecodes.BTN_SOUTH: "a",
        ecodes.BTN_EAST: "b",
        ecodes.BTN_NORTH: "x",
        ecodes.BTN_WEST: "y",
        ecodes.BTN_TL: "lb",
        ecodes.BTN_TR: "rb",
        ecodes.BTN_SELECT: "back",
        ecodes.BTN_START: "start",
        ecodes.BTN_THUMBL: "ls",
        ecodes.BTN_THUMBR: "rs",
    }

    DPAD_MAP = {
        (ecodes.ABS_HAT0X, 1): "right",
        (ecodes.ABS_HAT0X, -1): "left",
        (ecodes.ABS_HAT0Y, 1): "down",
        (ecodes.ABS_HAT0Y, -1): "up",
    }

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self):
        while True:
            dev = self._find_device()
            if not dev:
                self._reset()
                time.sleep(RECONNECT_INTERVAL)
                continue

            self.h["connected"] = True
            fd = dev.fd

            try:
                while True:
                    # Use select with timeout so we can detect shutdown
                    r, _, _ = select.select([fd], [], [], 0.1)
                    if not r:
                        # No events, just refresh jog outputs (deadzone
                        # param may have changed)
                        self._update_jog_outputs()
                        continue

                    for event in dev.read():
                        if event.type == ecodes.EV_ABS:
                            code = event.code

                            if code == ecodes.ABS_X:
                                val = self._scale_axis(code, event.value)
                                self._lx = val
                                self.h["lx"] = val
                            elif code == ecodes.ABS_Y:
                                val = self._scale_axis(code, event.value)
                                self._ly = -val  # invert Y
                                self.h["ly"] = -val
                            elif code == ecodes.ABS_RX:
                                val = self._scale_axis(code, event.value)
                                self.h["rx"] = val
                            elif code == ecodes.ABS_RY:
                                val = self._scale_axis(code, event.value)
                                self._ry = -val  # invert Y
                                self.h["ry"] = -val
                            elif code == ecodes.ABS_Z:
                                val = self._scale_trigger(code, event.value)
                                self.h["lt"] = val
                            elif code == ecodes.ABS_RZ:
                                val = self._scale_trigger(code, event.value)
                                self._rt = val
                                self.h["rt"] = val
                            elif code in (ecodes.ABS_HAT0X, ecodes.ABS_HAT0Y):
                                # D-pad as hat switch
                                for (dcode, dval), pin in self.DPAD_MAP.items():
                                    if dcode == code:
                                        self.h[pin] = (event.value == dval)

                            self._update_jog_outputs()

                        elif event.type == ecodes.EV_KEY:
                            pin = self.BUTTON_MAP.get(event.code)
                            if pin:
                                self.h[pin] = bool(event.value)

            except (OSError, IOError):
                # Controller disconnected
                self._reset()
                time.sleep(RECONNECT_INTERVAL)


if __name__ == "__main__":
    gp = GamepadShim()
    try:
        gp.run()
    except KeyboardInterrupt:
        pass
