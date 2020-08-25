"""
This file contains settings writen to the device each time it is connected.
"""

from device.registers import ControllerRegister as Ctl
from device.registers import CellRegister as Cell

controller_defaults = {
    Ctl.ccrc: 1,  # Always check CRC
}

# TODO: Write correct settings
# Some values may not work correctly (I do not have full documentation)
cell_defaults = {
    Cell.ccrc: 1,  # Always check CRC
    Cell.Ustdby: 0,  # Voltage in Stand By mode (current protection)
    Cell.prottim: 0,  # Current source mode when the protection is triggered
    Cell.keepVset: 0,  # Do not store voltage in eeprom
    Cell.ONonBOOT: 0,  # Do not turn on high voltage on boot
    Cell.HVOFFonIOPB: 1,  # Turn off high voltage on current overload
}
