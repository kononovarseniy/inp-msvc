import logging
from concurrent.futures import Future
from concurrent.futures.thread import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Generic, Tuple, List, Callable, TypeVar

from gi.repository import GObject, GLib

from device.device import DeviceAddress, Device, Cell

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
        self.actual = value
        if self.waiting > 0:
            self.desired = value


@dataclass
class CellState:
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

    # Constant values
    cell_index: int
    """Cell index, numbering from one"""
    voltage_range: Tuple[float, float]
    """Allowed voltage range"""
    current_limit_range: Tuple[float, float]
    """Allowed current limit range"""


def _read_full_cell_state(cell: Cell) -> CellState:
    return CellState(
        DeviceParameter(cell.is_output_voltage_enabled()),
        DeviceParameter(cell.get_output_voltage()),
        DeviceParameter(cell.get_current_limit()),
        DeviceParameter(cell.get_ramp_up_speed()),
        DeviceParameter(cell.get_ramp_down_speed()),
        cell.get_measured_voltage(),
        cell.get_measured_current(),
        cell.get_index(),
        cell.get_output_voltage_range(),
        cell.get_current_limit_range()
    )


def _read_full_state(device: Device) -> List[CellState]:
    return [_read_full_cell_state(cell) for cell in device.cells]


def _read_cell_state(cell: Cell) -> Tuple:
    return (
        cell.is_output_voltage_enabled(),
        cell.get_output_voltage(),
        cell.get_current_limit(),
        cell.get_ramp_up_speed(),
        cell.get_ramp_down_speed(),
        cell.get_measured_voltage(),
        cell.get_measured_current(),
    )


def _update_state(state: CellState, values: Tuple) -> None:
    state.enabled.update_value(values[0])
    state.voltage_set.update_value(values[1])
    state.current_limit.update_value(values[2])
    state.ramp_up_speed.update_value(values[3])
    state.ramp_down_speed.update_value(values[4])
    state.voltage_measured = values[5]
    state.current_measured = values[6]


def _read_state(device: Device) -> List[Tuple]:
    return [_read_cell_state(cell) for cell in device.cells]


def _connect(executor: ThreadPoolExecutor, address: DeviceAddress) -> 'Worker':
    dev = Device(address, CHANNEL_COUNT, SOCKET_TIMEOUT)
    state = _read_full_state(dev)
    return Worker(executor, dev, state)


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


class Worker(GObject.Object):
    """
    This class is responsible for asynchronous access to device parameters.

    It maintains a table of channel parameters, and provides methods to modify them.
    """
    CELL_UPDATED = 'cell-updated'
    UPDATED = 'updated'

    def __init__(self, executor: ThreadPoolExecutor, device: Device, state: List[CellState]):
        """This method is for internal use only. Use Worker.create(address) instead."""
        super().__init__()
        self._executor = executor
        self._device = device
        self._state = state
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

    def _on_modification_completed(self, f: Future, state: CellState, parameter: DeviceParameter):
        parameter.update_value(f.result())
        parameter.waiting -= 1
        self.emit(Worker.CELL_UPDATED, state.cell_index)

    def _start_modification(self,
                            cell_index: int,
                            parameter: DeviceParameter[T],
                            task: Callable[[Cell, T], T],
                            value: T):

        cell = self._device.cells[cell_index - 1]
        state = self._state[cell_index - 1]

        parameter.desired = value
        parameter.waiting += 1

        self._executor.submit(task, cell, value).add_done_callback(
            lambda f: GLib.idle_add(self._on_modification_completed, f, state, parameter))

        self.emit(Worker.CELL_UPDATED, state.cell_index)

    def set_enabled(self, cell_index: int, value: bool):
        state = self.get_cell_state(cell_index)
        self._start_modification(cell_index, state.enabled, _set_output_voltage_enabled, bool(value))

    def set_output_voltage(self, cell_index: int, value: float):
        state = self.get_cell_state(cell_index)
        l, h = state.voltage_range
        if value < l or value > h:
            raise ValueError(f'Cell #{cell_index}: Cannot set voltage to {value}. Allowed range is {l}..{h}')
        self._start_modification(cell_index, state.voltage_set, _set_voltage, value)

    def set_current_limit(self, cell_index: int, value: float):
        state = self.get_cell_state(cell_index)
        l, h = state.current_limit_range
        if value < l or value > h:
            raise ValueError(f'Cell #{cell_index}: Cannot set current limit to {value}. Allowed range is {l}..{h}')
        self._start_modification(cell_index, state.current_limit, _set_current_limit, value)

    def set_ramp_up_speed(self, cell_index: int, value: int):
        state = self.get_cell_state(cell_index)
        if value < 1:
            raise ValueError(f'Cell #{cell_index}: Cannot set ramp up speed: {value} is out of allowed range')
        self._start_modification(cell_index, state.ramp_up_speed, _set_ramp_up_speed, value)

    def set_ramp_down_speed(self, cell_index: int, value: int):
        state = self.get_cell_state(cell_index)
        if value < 1:
            raise ValueError(f'Cell #{cell_index}: Cannot set  ramp down speed: {value} is out of allowed range')
        self._start_modification(cell_index, state.ramp_down_speed, _set_ramp_down_speed, value)

    @GObject.Signal(name=CELL_UPDATED, arg_types=[int])
    def _on_cell_updated(self, index: int):
        pass

    @GObject.Signal(name=UPDATED)
    def _on_updated(self):
        pass

    def _on_update_completed(self, f: 'Future[List[Tuple]]'):
        res = f.result()
        for c, s in zip(self._state, res):
            _update_state(c, s)
            self.emit(Worker.CELL_UPDATED, c.cell_index)
        self.emit(Worker.UPDATED)

    def _on_timer(self):
        self._executor.submit(_read_state, self._device).add_done_callback(
            lambda f: GLib.idle_add(self._on_update_completed, f))
        return True

    def __str__(self):
        return f'<Worker {self._device.address}>'
