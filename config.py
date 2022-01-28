"""
This file contains program configuration.

Users are free to edit this file.
"""
import logging
import os
import sys

from device.registers import CellRegister as Cell
from device.registers import ControllerRegister as Ctl
from settings import check_settings, gui_settings, defaults, program_settings

"""
Logging configuration
"""

dirname = 'log'
if not os.path.exists(dirname):
    os.makedirs(dirname)

program_settings.data_log_file = 'log/values.csv'

# Configure logging to a file
file_handler = logging.FileHandler('log/log.log')
# stdout_handler.setLevel(logging.NOTSET)

# Configure logging to stdout
stdout_handler = logging.StreamHandler(sys.stdout)
# stdout_handler.setLevel(logging.WARNING)

logging.basicConfig(
    level=logging.NOTSET,
    format='%(asctime)s:%(levelname)s:%(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=(file_handler, stdout_handler)
)

"""
Global parameters
"""

check_settings.max_voltage_difference = 5
check_settings.max_voltage_when_off = 100000

gui_settings.window_title = 'Voltage controller'

defaults.controller = {
    Ctl.ccrc: 1,  # Always check CRC
}

# TODO: Write correct settings
# Some values may not work correctly (I do not have full documentation)
defaults.cell = {
    Cell.ccrc: 1,  # Always check CRC
    Cell.Ustdby: 0,  # Voltage in Stand By mode (current protection)
    Cell.prottim: 0,  # Current source mode when the protection is triggered
    Cell.keepVset: 0,  # Do not store voltage in eeprom
    Cell.ONonBOOT: 0,  # Do not turn on high voltage on boot
    Cell.HVOFFonIOPB: 1,  # Turn off high voltage on current overload
}
