"""Coolant / mist user button for the PM-940.

Restores the Mist toggle that Probe Basic 0.6.0 had in its main layout and
0.6.8 dropped from probe_basic.ui (it survives only in probe_basic_vertical.ui,
which this machine does not use). See coolant_buttons.ui for the full rationale
and the HAL mapping - in short, coolant.flood.toggle is what physically drives
the mist on this machine.

Probe Basic discovers this via [DISPLAY]USER_BUTTONS_PATH and requires:
  - the folder name and the .py filename to match (coolant_buttons/coolant_buttons.py)
  - a class named exactly `UserButton`
"""

import os

from qtpy import uic
from qtpy.QtWidgets import QWidget

from qtpyvcp.utilities import logger

LOG = logger.getLogger(__name__)


class UserButton(QWidget):
    def __init__(self, parent=None):
        super(UserButton, self).__init__(parent)
        ui_file = os.path.splitext(os.path.basename(__file__))[0] + ".ui"
        uic.loadUi(os.path.join(os.path.dirname(__file__), ui_file), self)
