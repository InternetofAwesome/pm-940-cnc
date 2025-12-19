import os
import linuxcnc

from qtpy import uic
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QWidget

from qtpyvcp.plugins import getPlugin
from qtpyvcp.utilities import logger

LOG = logger.getLogger(__name__)

STATUS = getPlugin('status')
TOOL_TABLE = getPlugin('tooltable')

INI_FILE = linuxcnc.ini(os.getenv('INI_FILE_NAME'))

class UserTab(QWidget):
    def __init__(self, parent=None):
        super(UserTab, self).__init__(parent)
        ui_file = os.path.splitext(os.path.basename(__file__))[0] + ".ui"
        uic.loadUi(os.path.join(os.path.dirname(__file__), ui_file), self)

        # Connect the Spindle Nose Touch Off button
        if hasattr(self, 'btnSpindleNoseTouchOff'):
            self.btnSpindleNoseTouchOff.clicked.connect(self.spindle_nose_touch_off)

    def spindle_nose_touch_off(self):
        """
        Run the spindle nose touch off subroutine via MDI command.
        """
        try:
            c = linuxcnc.command()
            # Make sure machine is on and in MDI mode
            # Run the subroutine (assuming o<spindle_nose_touch_off> is loaded and available)
            c.mode(linuxcnc.MODE_MDI)
            c.wait_complete()
            c.mdi("o<spindle_nose_touch_off> call")
            LOG.info("Spindle Nose Touch Off subroutine called.")
        except Exception as e:
            LOG.error(f"Failed to run spindle nose touch off: {e}")
