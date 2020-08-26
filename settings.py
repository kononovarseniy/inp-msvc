"""
This file contains definitions of settings used by the program and their default values.

It is not supposed to be edited by user, edit config.py instead.
"""

from dataclasses import dataclass
from typing import Dict

from device.registers import ControllerRegister, CellRegister


@dataclass
class GuiSettings:
    window_title: str


gui_settings = GuiSettings('Voltage controller')


@dataclass
class DefaultValues:
    controller: Dict[ControllerRegister, int]
    cell: Dict[CellRegister, int]


defaults = DefaultValues(
    controller={},
    cell={}
)


@dataclass
class CheckSettings:
    max_voltage_difference: float
    """Maximal allowed difference between desired and actual voltage"""
    max_voltage_when_off: float
    """Maximal allowed voltage when high voltage is disabled"""


check_settings = CheckSettings(
    max_voltage_difference=1,
    max_voltage_when_off=10
)
