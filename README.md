# PM-940 CNC LinuxCNC Configuration

LinuxCNC 2.9 (Master) configuration for a PM-940 milling machine with closed-loop stepper control.

## Hardware

- **Controller**: Mesa 7C80 (Raspberry Pi SPI interface)
- **Axes**: 3-axis (X, Y, Z) closed-loop steppers with encoder feedback
- **Encoders**: 5080 counts/inch (X, Y), -5080 counts/inch (Z)
- **Spindle**: PWM-controlled via Mesa PWMgen, PID-regulated
- **Probing**: Touch probe + tool setter (OR'd together via `probeor`)
- **E-stop**: Hardware e-stop via Mesa input (inmux.00.input-10)
- **GUI**: Probe Basic (qtpyvcp)
- **Units**: Imperial (inches)

## Project Structure

```
pm-940-cnc/
├── pm940.ini                    # Machine configuration
├── pm940.hal                    # Main HAL file (axes, PID, I/O, jog wiring)
├── probe_basic_postgui.hal      # Post-GUI HAL (oiler, idle shutdown, cycle timer)
├── oiler.hal                    # Standalone oiler config (unused, superseded by postgui)
├── custom_config.yml            # qtpyvcp GUI configuration
├── tool.tbl                     # Tool table
├── oiler_hal_component/         # Automatic way oiler (realtime HAL comp)
│   ├── oiler.comp
│   └── build.sh
├── idle_shutdown_hal_component/ # Inactivity auto-shutdown (realtime HAL comp)
│   ├── idle_shutdown.comp
│   └── build.sh
├── subroutines/                 # NGC macro subroutines (~95 files)
│   ├── tool_change*.ngc         # Tool change routines
│   ├── probe_*.ngc              # Probing routines
│   └── ...
├── python/                      # Python support modules
│   ├── stdglue.py               # Standard glue (remap support)
│   ├── remap.py                 # G-code remapping
│   └── toplevel.py              # Python toplevel init
├── user_tabs/                   # Custom qtpyvcp GUI tabs
│   ├── spindle_nose_touch_off/  # Spindle nose touch-off tab
│   └── template_main/           # Template main tab
└── solidworks-post-processor/   # CAM post-processor files
```

## Custom HAL Components

### Automatic Oiler (`oiler_hal_component/oiler.comp`)

Realtime HAL component that triggers the way oiler pump based on distance traveled or elapsed motion time.

**Triggers when any of:**
- Distance traveled >= 1000 inches (`dist-thresh`)
- Motion time accumulated >= 3600 seconds (`time-thresh`)
- Machine finishes homing (one-shot)
- Manual trigger pin asserted

**Behavior:** Runs pump for 10 seconds (`pump-time`), then locks out for 120 seconds to prevent rapid re-triggering.

**HAL wiring** (in `probe_basic_postgui.hal`):
```
                              ┌─────────┐
joint.0/1/2.pos-fb ──────────►│         │
                              │  oiler  │──── pump ──► hm2_7c80.0.ssr.00.out-04
motion.current-vel ──► abs ──►│         │
  comp (>0.001) ─────────────►│         │
motion.is-all-homed ─────────►│         │
                              └─────────┘
```

### Idle Shutdown (`idle_shutdown_hal_component/idle_shutdown.comp`)

Realtime HAL component that turns the machine off after a configurable period of inactivity. Prevents the machine from being left on unattended.

**Activity inputs** (any one resets the idle timer):

| Input Pin        | Connected To               | Detects                    |
|------------------|----------------------------|----------------------------|
| `current_vel`    | `motion.current-vel`       | Any axis motion            |
| `program_running`| `halui.program.is-running` | G-code program executing   |
| `program_paused` | `halui.program.is-paused`  | Program paused (still "in use") |
| `spindle_on`     | `spindle.0.on`             | Spindle turning            |
| `user_activity`  | *(unconnected — available)*| Generic catch-all for future use |

**Outputs:**

| Pin        | Connected To        | Purpose                              |
|------------|---------------------|--------------------------------------|
| `shutdown` | `halui.machine.off` | Turns machine off when timeout fires |
| `idle`     | *(observable)*      | True while idle timer is counting    |

**Parameters:**

| Param          | Default | Description                            |
|----------------|---------|----------------------------------------|
| `timeout`      | 1800    | Seconds of inactivity before shutdown (30 min) |
| `idle_seconds` | 0       | Current idle time (readable for debugging via halshow) |

**Behavior:**
1. While machine is off: timer stays at zero, no action
2. While machine is on and any activity input is active: timer resets to zero
3. While machine is on and all inputs are idle: timer accumulates
4. When timer >= timeout: `shutdown` pin goes true, triggering `halui.machine.off`
5. Machine turns off, timer resets — user can press Machine On to resume

**HAL wiring** (in `probe_basic_postgui.hal`):
```
                                ┌──────────────────┐
motion.current-vel ────────────►│                  │
halui.program.is-running ──────►│                  │
halui.program.is-paused ───────►│ idle_shutdown    │──── shutdown ──► halui.machine.off
spindle.0.on ──────────────────►│                  │
halui.machine.is-on ───────────►│                  │
                                └──────────────────┘
```

### Building Custom Components

On the CNC machine (requires `halcompile` from the LinuxCNC dev package):

```bash
cd idle_shutdown_hal_component && sudo bash build.sh
cd oiler_hal_component && sudo bash build.sh
```

## HAL File Organization

### `pm940.hal` — Main HAL

Loaded first. Handles:
- Mesa 7C80 hostmot2 driver loading and pin aliasing
- Servo thread function chain: `hm2 read → motion-command-handler → motion-controller → PID calcs → hm2 write`
- Closed-loop stepper control (PID + stepgen in velocity mode + encoder feedback)
- Spindle PID and PWM control
- HALUI signal wiring (jog, axis select, spindle manual controls)
- Drive enables (`machine-is-on` → SSR outputs for X/Y and Z drives)
- Probe signal OR (touch probe + tool setter)

### `probe_basic_postgui.hal` — Post-GUI HAL

Loaded after the GUI starts (has access to qtpyvcp pins). Handles:
- Cycle timer (for job time display)
- Manual tool change dialog signals
- Probe LED indicator
- Hardware e-stop wiring
- Oiler component loading and wiring
- Idle shutdown component loading and wiring

## Branches

| Branch       | Purpose                                              |
|--------------|------------------------------------------------------|
| `master`     | Stable configuration (includes oiler, idle shutdown)  |
| `8bitdo`     | Bluetooth gamepad (8Bitdo) jogging via `game_controller.py` — WIP |

## Key INI Settings

```ini
[TRAJ]
LINEAR_UNITS       = inch
MAX_LINEAR_VELOCITY = 1.7        # in/s — maximum rapid
DEFAULT_LINEAR_VELOCITY = 1.1    # in/s — default jog/rapid speed

[AXIS_X] / [AXIS_Y]
MAX_VELOCITY       = 1.666       # in/s
MAX_ACCELERATION   = 40          # in/s²

[AXIS_Z]
MAX_VELOCITY       = 1.666       # in/s
MAX_ACCELERATION   = 9           # in/s²

[EMCMOT]
SERVO_PERIOD       = 1000000     # 1 ms servo thread
```
