import logging
from concurrent.futures import Future
from concurrent.futures.thread import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Generic, Tuple, List, Callable, TypeVar, Optional

from gi.repository import GObject, GLib

from device.device import DeviceAddress, Device, Cell, Controller
from device.registers import CellCSR, ControllerSR, TemperatureSensor

CHANNEL_COUNT = 16

SOCKET_TIMEOUT = 10

LOGGER = logging.getLogger('gui.worker')

T = TypeVar('T')


class DeviceParameter(Generic[T]):
    def __init__(self, desired: T, actual: T = None, waiting: int = 0):
        self.desired = desired
        self.actual = actual if actual is not None else desired
        self.waiting = waiting

    def update_value(self, value: T) -> None:
        """Update the actual value. If there are pending write commands, then do not change the desired value.
        If no write commands were received, then change the requested value too"""
        self.actual = value
        if self.waiting > 0:
            self.desired = value

    def set_actual_dec_waiting(self, value: T):
        self.actual = value
        self.waiting -= 1

    def set_desired_inc_waiting(self, value: T):
        self.desired = value
        self.waiting += 1


@dataclass
class CellState:
    """Cell state includes constant cell parameters, cell state and changeable parameters with their desired values"""
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

    # Readonly values
    voltage_measured: float
    """Measured output voltage in volts"""
    current_measured: float
    """Measured current in uA"""
    csr: CellCSR
    """Cell control, status register"""

    # Constant values
    cell_index: int
    """Cell index, numbering from one"""
    voltage_range: Tuple[float, float]
    """Allowed voltage range"""
    current_limit_range: Tuple[float, float]
    """Allowed current limit range"""


@dataclass
class CellSettings:
    """Contains values of writable cell parameters"""
    enabled: bool
    voltage: float
    current_limit: float
    ramp_up: int
    ramp_down: int


@dataclass
class CellValues(CellSettings):
    """Contains values that represent cell status"""
    voltage_measured: float
    current_measured: float
    csr: CellCSR


@dataclass
class ControllerState:
    base_voltage_enabled: DeviceParameter[bool]
    fan_off_temp: DeviceParameter[int]
    fan_on_temp: DeviceParameter[int]
    shutdown_temp: DeviceParameter[int]
    temp_sensor: DeviceParameter[TemperatureSensor]

    status: ControllerSR
    processor_temp: int
    board_temp: int
    power_supply_temp: int
    low_voltage: float
    base_voltage: float


@dataclass
class ControllerSettings:
    base_voltage_on: bool
    fan_off_temp: int
    fan_on_temp: int
    shutdown_temp: int
    temp_sensor: TemperatureSensor


@dataclass
class ControllerValues(ControllerSettings):
    status: ControllerSR
    processor_temp: int
    board_temp: int
    power_supply_temp: int
    low_voltage: float
    base_voltage: float


def _read_controller_values(ctl: Controller) -> ControllerValues:
    return ControllerValues(
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


def _read_controller_state(ctl: Controller) -> ControllerState:
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


def _read_cell_state(cell: Cell) -> CellState:
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
        cell.get_output_voltage_range(),
        cell.get_current_limit_range()
    )


def _read_cell_values(cell: Cell) -> CellValues:
    return CellValues(
        cell.is_output_voltage_enabled(),
        cell.get_output_voltage(),
        cell.get_current_limit(),
        cell.get_ramp_up_speed(),
        cell.get_ramp_down_speed(),
        cell.get_measured_voltage(),
        cell.get_measured_current(),
        cell.get_csr()
    )


def _read_device_values(device: Device) -> Tuple[ControllerValues, List[CellValues]]:
    return _read_controller_values(device.controller), list(map(_read_cell_values, device.cells))


def _read_device_state(device: Device) -> Tuple[ControllerState, List[CellState]]:
    return _read_controller_state(device.controller), list(map(_read_cell_state, device.cells))


def _update_controller_state(state: ControllerState, values: ControllerValues) -> None:
    state.base_voltage_enabled.update_value(values.base_voltage_on)
    state.fan_off_temp.update_value(values.fan_off_temp)
    state.fan_on_temp.update_value(values.fan_on_temp)
    state.temp_sensor.update_value(values.temp_sensor)

    state.status = values.status
    state.processor_temp = values.processor_temp
    state.board_temp = values.board_temp
    state.power_supply_temp = values.power_supply_temp
    state.low_voltage = values.low_voltage
    state.base_voltage = values.base_voltage


def _update_cell_state(state: CellState, values: CellValues) -> None:
    state.enabled.update_value(values.enabled)
    state.voltage_set.update_value(values.voltage)
    state.current_limit.update_value(values.current_limit)
    state.ramp_up_speed.update_value(values.ramp_up)
    state.ramp_down_speed.update_value(values.ramp_down)

    state.voltage_measured = values.voltage_measured
    state.current_measured = values.current_measured
    state.csr = values.csr


def _connect(executor: ThreadPoolExecutor, address: DeviceAddress) -> 'Worker':
    dev = Device(address, CHANNEL_COUNT, SOCKET_TIMEOUT)
    ctl, cells = _read_device_state(dev)
    return Worker(executor, dev, ctl, cells)


def _set_output_voltage_enabled(cell: Cell, value: bool) -> bool:
    cell.set_output_voltage_enabled(value)
    return cell.is_output_voltage_enabled()


def _set_voltage(cell: Cell, value: float) -> float:
    cell.set_output_voltage(value)
    return cell.get_output_voltage()


def _set_current_limit(cell: Cell, value: float) -> float:
    cell.set_current_limit(value)
    return cell.get_current_limit()


def _set_ramp_up_speed(cell: Cell, value: int) -> int:
    cell.set_ramp_up_speed(value)
    return cell.get_ramp_up_speed()


def _set_ramp_down_speed(cell: Cell, value: int) -> int:
    cell.set_ramp_down_speed(value)
    return cell.get_ramp_down_speed()


def _apply_cell_settings(cell: Cell, settings: CellSettings) -> CellSettings:
    return CellSettings(
        _set_output_voltage_enabled(cell, settings.enabled),
        _set_voltage(cell, settings.voltage),
        _set_current_limit(cell, settings.current_limit),
        _set_ramp_up_speed(cell, settings.ramp_up),
        _set_ramp_down_speed(cell, settings.ramp_down)
    )


def _apply_controller_settings(ctl: Controller, settings: ControllerSettings) -> ControllerSettings:
    return ControllerSettings(
        ctl.set_base_voltage_enabled(settings.base_voltage_on),
        ctl.set_fan_off_temperature(settings.fan_off_temp),
        ctl.set_fan_on_temperature(settings.fan_on_temp),
        ctl.set_shutdown_temperature(settings.shutdown_temp),
        ctl.set_temperature_sensor(settings.temp_sensor)
    )


def check_voltage_value(state: CellState, value: float):
    l, h = state.voltage_range
    if value < l or value > h:
        raise ValueError(f'Cell #{state.cell_index}: Cannot set voltage to {value}. Allowed range is {l}..{h}')


def check_current_value(state: CellState, value: float):
    l, h = state.current_limit_range
    if value < l or value > h:
        raise ValueError(f'Cell #{state.cell_index}: Cannot set current limit to {value}. Allowed range is {l}..{h}')


def check_ramp_up_value(state: CellState, value: int):
    if value < 1:
        raise ValueError(f'Cell #{state.cell_index}: Cannot set ramp up speed: {value} is out of allowed range')


def check_ramp_down_value(state: CellState, value: int):
    if value < 1:
        raise ValueError(f'Cell #{state.cell_index}: Cannot set ramp down speed: {value} is out of allowed range')


class Worker(GObject.Object):
    """
    This class is responsible for asynchronous access to device parameters.

    It maintains a table of channel parameters, and provides methods to modify them.
    """
    CELL_UPDATED = 'cell-updated'
    UPDATED = 'updated'
    CONTROLLER_UPDATED = 'controller-updated'

    def __init__(self, executor: ThreadPoolExecutor, device: Device,
                 ctl_state: ControllerState, cells_state: List[CellState]):
        """This method is for internal use only. Use Worker.create(address) instead."""
        super().__init__()
        self._executor = executor
        self._device = device
        self._state = cells_state
        self._controller_state = ctl_state
        GLib.timeout_add(10000, self._on_timer)

    def get_device_address(self) -> DeviceAddress:
        return self._device.address

    @staticmethod
    def create(address: DeviceAddress) -> 'Future[Worker]':
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=str(address))
        return executor.submit(_connect, executor, address)

    def close(self) -> 'Future[None]':
        if self._executor is None:
            raise RuntimeError('Illegal worker state')

        f = self._executor.submit(self._device.close)
        self._executor.shutdown(wait=False)
        self._executor = None
        self._device = None
        return f

    def get_cell_count(self):
        return len(self._state)

    def get_cell_state(self, cell_index: int) -> CellState:
        """
        Get reference to an object that represents the current state of the cell with given index.

        This method always return same object for the same cell.
        Fields of the returned object may be modified by worker, but you should not modify them.

        :param cell_index: Index of the cell, numbering from 1.

        :return: Current state of the cell.
        """
        if cell_index < 1 or cell_index > len(self._state):
            raise IndexError(f'Invalid cell index: {cell_index}')
        return self._state[cell_index - 1]

    def iter_cells(self):
        for s in self._state:
            yield s

    def get_controller_state(self) -> ControllerState:
        return self._controller_state

    def _on_modification_completed(self, f: Future, state: CellState, parameter: DeviceParameter):
        parameter.set_actual_dec_waiting(f.result())
        self.emit(Worker.CELL_UPDATED, state.cell_index)

    def _start_modification(self, cell_index: int, parameter: DeviceParameter[T],
                            task: Callable[[Cell, T], T], value: T):
        cell = self._device.cells[cell_index - 1]
        state = self._state[cell_index - 1]

        parameter.set_desired_inc_waiting(value)

        self._executor.submit(task, cell, value).add_done_callback(
            lambda f: GLib.idle_add(self._on_modification_completed, f, state, parameter))

        self.emit(Worker.CELL_UPDATED, state.cell_index)

    def _on_ctl_modification_completed(self, f: Future, parameter: DeviceParameter):
        parameter.set_actual_dec_waiting(f.result())
        self.emit(Worker.CONTROLLER_UPDATED)

    def _start_ctl_modification(self, parameter: DeviceParameter[T], task: Callable[[Controller, T], T], value: T):
        parameter.set_desired_inc_waiting(value)

        self._executor.submit(task, self._device.controller, value).add_done_callback(
            lambda f: GLib.idle_add(self._on_ctl_modification_completed, f, parameter))

        self.emit(Worker.CONTROLLER_UPDATED)

    def _on_cell_modification_completed(self, f: Future, state: CellState):
        settings: CellSettings = f.result()
        state.enabled.set_actual_dec_waiting(settings.enabled)
        state.voltage_set.set_actual_dec_waiting(settings.voltage)
        state.current_limit.set_actual_dec_waiting(settings.current_limit)
        state.ramp_up_speed.set_actual_dec_waiting(settings.ramp_up)
        state.ramp_down_speed.set_actual_dec_waiting(settings.ramp_down)
        self.emit(Worker.CELL_UPDATED, state.cell_index)

    def _start_cell_modification(self, cell_index: int, settings: CellSettings):
        cell = self._device.cells[cell_index - 1]
        state = self._state[cell_index - 1]

        self._executor.submit(_apply_cell_settings, cell, settings).add_done_callback(
            lambda f: GLib.idle_add(self._on_cell_modification_completed, f, state))

    def set_enabled(self, cell_index: int, value: bool):
        state = self.get_cell_state(cell_index)
        self._start_modification(cell_index, state.enabled, _set_output_voltage_enabled, bool(value))

    def set_output_voltage(self, cell_index: int, value: float):
        state = self.get_cell_state(cell_index)
        check_voltage_value(state, value)
        self._start_modification(cell_index, state.voltage_set, _set_voltage, value)

    def set_current_limit(self, cell_index: int, value: float):
        state = self.get_cell_state(cell_index)
        check_current_value(state, value)
        self._start_modification(cell_index, state.current_limit, _set_current_limit, value)

    def set_ramp_up_speed(self, cell_index: int, value: int):
        state = self.get_cell_state(cell_index)
        check_ramp_up_value(state, value)
        self._start_modification(cell_index, state.ramp_up_speed, _set_ramp_up_speed, value)

    def set_ramp_down_speed(self, cell_index: int, value: int):
        state = self.get_cell_state(cell_index)
        check_ramp_down_value(state, value)
        self._start_modification(cell_index, state.ramp_down_speed, _set_ramp_down_speed, value)

    def apply_settings_to_cells(self, values: List[Tuple[int, CellSettings]]) -> None:
        """
        Set parameters of all device channels.

        :param values: a list of tuples of the form (cell_index, enabled, voltage, current_limit, ramp_up, ramp_down).
        Cells that are not listed are disabled.

        :raises IndexError: the voltage cell with specified index does not exist.
        :raises ValueError: when some values are invalid.
        """

        # Check values and restore order
        new_values: List[Optional[CellSettings]] = [None] * len(self._state)
        for cell_index, settings in values:
            state = self.get_cell_state(cell_index)
            check_voltage_value(state, settings.voltage)
            check_current_value(state, settings.current_limit)
            check_ramp_up_value(state, settings.ramp_up)
            check_ramp_down_value(state, settings.ramp_down)
            new_values[cell_index - 1] = settings

        # Set desired values and start modification
        for cell, settings in zip(self._state, new_values):
            if settings is None:
                self.set_enabled(cell.cell_index, False)
            else:
                cell.enabled.set_desired_inc_waiting(settings.enabled)
                cell.voltage_set.set_desired_inc_waiting(settings.voltage)
                cell.current_limit.set_desired_inc_waiting(settings.current_limit)
                cell.ramp_up_speed.set_desired_inc_waiting(settings.ramp_up)
                cell.ramp_down_speed.set_desired_inc_waiting(settings.ramp_down)
                self._start_cell_modification(cell.cell_index, settings)

    def set_base_voltage_enabled(self, enabled: bool):
        self._start_ctl_modification(self._controller_state.base_voltage_enabled,
                                     Controller.set_base_voltage_enabled, enabled)

    def set_fan_off_temp(self, value: int):
        self._start_ctl_modification(self._controller_state.fan_off_temp,
                                     Controller.set_fan_off_temperature, value)

    def set_fan_on_temp(self, value: int):
        self._start_ctl_modification(self._controller_state.fan_on_temp,
                                     Controller.set_fan_on_temperature, value)

    def set_shutdown_temp(self, value: int):
        self._start_ctl_modification(self._controller_state.shutdown_temp,
                                     Controller.set_shutdown_temperature, value)

    def set_temp_sensor(self, sensor: TemperatureSensor):
        self._start_ctl_modification(self._controller_state.temp_sensor,
                                     Controller.set_temperature_sensor, sensor)

    @GObject.Signal(name=CELL_UPDATED, arg_types=[int])
    def _on_cell_updated(self, index: int):
        pass

    @GObject.Signal(name=UPDATED)
    def _on_updated(self):
        pass

    @GObject.Signal(name=CONTROLLER_UPDATED)
    def _on_controller_updated(self):
        pass

    def _on_update_completed(self, f: 'Future[Tuple[ControllerValues, List[CellValues]]]'):
        ctl, cells = f.result()
        _update_controller_state(self._controller_state, ctl)
        self.emit(Worker.CONTROLLER_UPDATED)
        for c, s in zip(self._state, cells):
            _update_cell_state(c, s)
            self.emit(Worker.CELL_UPDATED, c.cell_index)
        self.emit(Worker.UPDATED)

    def _on_timer(self):
        self._executor.submit(_read_device_values, self._device).add_done_callback(
            lambda f: GLib.idle_add(self._on_update_completed, f))
        return True

    def __str__(self):
        return f'<Worker {self._device.address}>'
