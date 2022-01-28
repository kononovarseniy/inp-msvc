"""
This file contains class definitions used to store the current state of devices.
The functions defined here serve to transform the various representations of these states,
and to read and write them to the device.
"""
from dataclasses import dataclass
from typing import Tuple, Generic, TypeVar

from device.device import Cell, Controller
from device.registers import CellCSR, TemperatureSensor, ControllerSR

T = TypeVar('T')


class DeviceParameter(Generic[T]):
    """
    This class stores state of single mutable device parameter.
    It contains three fields:

    - desired value -- the value that is set from user interface,
    - actual value -- the value read from device,
    - waiting counter -- number of pending writes.

    If waiting counter is 0 the update_value() sets the desired value.
    This way, if there are no pending writes, the desired value remains in sync with the actual value.
    """

    def __init__(self, desired: T, actual: T = None, waiting: int = 0):
        self.desired = desired
        self.actual = actual if actual is not None else desired
        self.waiting = waiting

    def update_value(self, value: T) -> None:
        """Update the actual value. If there are pending write commands, then do not change the desired value.
        If no write commands were received, then change the requested value too"""
        self.actual = value
        if self.waiting == 0:
            self.desired = value

    def set_actual_dec_waiting(self, value: T):
        self.actual = value
        self.waiting -= 1

    def set_desired_inc_waiting(self, value: T):
        self.desired = value
        self.waiting += 1


@dataclass
class _CellParameters:
    """Mutable cell parameters"""

    enabled: DeviceParameter[bool]
    """Indicates whether the output voltage is on"""
    voltage_set: DeviceParameter[float]
    """Output voltage in volts"""
    current_limit: DeviceParameter[float]
    """Current limit in uA"""
    ramp_up_speed: DeviceParameter[int]
    """Ramp up speed in V/s"""
    ramp_down_speed: DeviceParameter[int]
    """Ramp down sped in V/s"""


@dataclass
class _CellParametersPlain:
    """Same mutable parameters as in _CellParameters, but without their desired values"""

    enabled: bool
    """Indicates whether the output voltage is on"""
    voltage_set: float
    """Output voltage in volts"""
    current_limit: float
    """Current limit in uA"""
    ramp_up_speed: int
    """Ramp up speed in V/s"""
    ramp_down_speed: int
    """Ramp down sped in V/s"""


@dataclass
class _CellReadonly:
    """Readonly cell parameters"""

    voltage_measured: float
    """Measured output voltage in volts"""
    current_measured: float
    """Measured current in uA"""
    csr: CellCSR
    """Cell control, status register"""


@dataclass
class _CellConstants:
    """Constant cell parameters, these parameters do not change during device operation"""

    voltage_range: Tuple[float, float]
    """Allowed voltage range"""
    current_limit_range: Tuple[float, float]
    """Allowed current limit range"""
    measured_voltage_range: Tuple[float, float]
    """Measured voltage range"""
    measured_current_range: Tuple[float, float]
    """Measured current range"""


@dataclass
class _CellAuxiliary:
    """Parameters not presented in the cell, but used by the program"""

    cell_index: int
    """Cell index, numbering from one"""
    counter_number: str
    """Counter number"""
    auto_enable: bool
    """If True the cell can be enabled automatically"""


@dataclass
class CellState(_CellConstants, _CellAuxiliary, _CellReadonly, _CellParameters):  # Reverse order
    """Cell state includes constant cell parameters, cell state and changeable parameters with their desired values"""


@dataclass
class CellUpdates(_CellReadonly, _CellParametersPlain):  # Reverse order
    """Contains values that represent cell status"""


@dataclass
class CellSettings(_CellParametersPlain):
    """Contains values of writable cell parameters"""

    counter_number: str
    """Counter number"""
    auto_enable: bool
    """If True the cell can be enabled automatically"""


def read_cell_state(cell: Cell) -> CellState:
    return CellState(
        DeviceParameter(cell.is_output_voltage_enabled()),
        DeviceParameter(cell.get_output_voltage()),
        DeviceParameter(cell.get_current_limit()),
        DeviceParameter(cell.get_ramp_up_speed()),
        DeviceParameter(cell.get_ramp_down_speed()),

        cell.get_measured_voltage(),
        cell.get_measured_current(),
        cell.get_csr(),

        cell.get_index(),
        "",
        False,

        cell.get_output_voltage_range(),
        cell.get_current_limit_range(),
        cell.get_measured_voltage_range(),
        cell.get_measured_current_range()
    )


def read_cell_updates(cell: Cell) -> CellUpdates:
    return CellUpdates(
        cell.is_output_voltage_enabled(),
        cell.get_output_voltage(),
        cell.get_current_limit(),
        cell.get_ramp_up_speed(),
        cell.get_ramp_down_speed(),
        cell.get_measured_voltage(),
        cell.get_measured_current(),
        cell.get_csr()
    )


def write_cell_settings(cell: Cell, settings: CellSettings) -> CellSettings:
    return CellSettings(
        cell.set_output_voltage_enabled(settings.enabled),
        cell.set_output_voltage(settings.voltage_set),
        cell.set_current_limit(settings.current_limit),
        cell.set_ramp_up_speed(settings.ramp_up_speed),
        cell.set_ramp_down_speed(settings.ramp_down_speed),
        settings.counter_number,
        settings.auto_enable
    )


def update_cell_state(state: CellState, values: CellUpdates) -> None:
    state.enabled.update_value(values.enabled)
    state.voltage_set.update_value(values.voltage_set)
    state.current_limit.update_value(values.current_limit)
    state.ramp_up_speed.update_value(values.ramp_up_speed)
    state.ramp_down_speed.update_value(values.ramp_down_speed)

    state.voltage_measured = values.voltage_measured
    state.current_measured = values.current_measured
    state.csr = values.csr


def update_desired_state(state: CellState, settings: CellSettings) -> None:
    state.enabled.set_desired_inc_waiting(settings.enabled)
    state.voltage_set.set_desired_inc_waiting(settings.voltage_set)
    state.current_limit.set_desired_inc_waiting(settings.current_limit)
    state.ramp_up_speed.set_desired_inc_waiting(settings.ramp_up_speed)
    state.ramp_down_speed.set_desired_inc_waiting(settings.ramp_down_speed)
    state.counter_number = settings.counter_number
    state.auto_enable = settings.auto_enable


def update_actual_state(state: CellState, settings: CellSettings) -> None:
    state.enabled.set_actual_dec_waiting(settings.enabled)
    state.voltage_set.set_actual_dec_waiting(settings.voltage_set)
    state.current_limit.set_actual_dec_waiting(settings.current_limit)
    state.ramp_up_speed.set_actual_dec_waiting(settings.ramp_up_speed)
    state.ramp_down_speed.set_actual_dec_waiting(settings.ramp_down_speed)
    state.counter_number = settings.counter_number
    state.auto_enable = settings.auto_enable


@dataclass
class _ControllerParameters:
    """Mutable controller parameters"""

    base_voltage_enabled: DeviceParameter[bool]
    fan_off_temp: DeviceParameter[int]
    fan_on_temp: DeviceParameter[int]
    shutdown_temp: DeviceParameter[int]
    temp_sensor: DeviceParameter[TemperatureSensor]


@dataclass
class _ControllerParametersPlain:
    """Same mutable parameters as in _ControllerParameters, but without their desired values"""

    base_voltage_enabled: bool
    fan_off_temp: int
    fan_on_temp: int
    shutdown_temp: int
    temp_sensor: TemperatureSensor


@dataclass
class _ControllerReadonly:
    """Readonly controller parameters"""

    status: ControllerSR
    processor_temp: int
    board_temp: int
    power_supply_temp: int
    low_voltage: float
    base_voltage: float


@dataclass
class ControllerState(_ControllerReadonly, _ControllerParameters):
    """Cell state includes constant cell parameters, cell state and changeable parameters with their desired values"""


@dataclass
class ControllerSettings(_ControllerParametersPlain):
    """Contains values of writable controller parameters"""


@dataclass
class ControllerUpdates(_ControllerReadonly, _ControllerParametersPlain):
    """Contains values that represent controller status"""


def read_controller_state(ctl: Controller) -> ControllerState:
    return ControllerState(
        DeviceParameter(ctl.get_base_voltage_enabled()),
        DeviceParameter(ctl.get_fan_off_temperature()),
        DeviceParameter(ctl.get_fan_on_temperature()),
        DeviceParameter(ctl.get_shutdown_temperature()),
        DeviceParameter(ctl.get_temperature_sensor()),
        ctl.get_status(),
        ctl.get_processor_temperature(),
        ctl.get_board_temperature(),
        ctl.get_power_supply_temperature(),
        ctl.get_low_voltage(),
        ctl.get_base_voltage()
    )


def read_controller_updates(ctl: Controller) -> ControllerUpdates:
    return ControllerUpdates(
        ctl.get_base_voltage_enabled(),
        ctl.get_fan_off_temperature(),
        ctl.get_fan_on_temperature(),
        ctl.get_shutdown_temperature(),
        ctl.get_temperature_sensor(),
        ctl.get_status(),
        ctl.get_processor_temperature(),
        ctl.get_board_temperature(),
        ctl.get_power_supply_temperature(),
        ctl.get_low_voltage(),
        ctl.get_base_voltage()
    )


def write_controller_settings(ctl: Controller, settings: ControllerSettings) -> ControllerSettings:
    return ControllerSettings(
        ctl.set_base_voltage_enabled(settings.base_voltage_enabled),
        ctl.set_fan_off_temperature(settings.fan_off_temp),
        ctl.set_fan_on_temperature(settings.fan_on_temp),
        ctl.set_shutdown_temperature(settings.shutdown_temp),
        ctl.set_temperature_sensor(settings.temp_sensor)
    )


def update_controller_state(state: ControllerState, values: ControllerUpdates) -> None:
    state.base_voltage_enabled.update_value(values.base_voltage_enabled)
    state.fan_off_temp.update_value(values.fan_off_temp)
    state.fan_on_temp.update_value(values.fan_on_temp)
    state.temp_sensor.update_value(values.temp_sensor)

    state.status = values.status
    state.processor_temp = values.processor_temp
    state.board_temp = values.board_temp
    state.power_supply_temp = values.power_supply_temp
    state.low_voltage = values.low_voltage
    state.base_voltage = values.base_voltage
