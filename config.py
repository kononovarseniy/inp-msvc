"""
This file contains program configuration.

Users are free to edit this file.
"""
import logging

from device.registers import CellRegister as Cell
from device.registers import ControllerRegister as Ctl
from settings import check_settings, gui_settings, defaults

logging.basicConfig(
    level=logging.NOTSET,
    # filename='log.log',
    format='%(asctime)s:%(levelname)s:%(module)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

check_settings.max_voltage_difference = 1
check_settings.max_voltage_when_off = 10

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
