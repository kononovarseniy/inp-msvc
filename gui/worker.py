import logging
from concurrent.futures import Future, CancelledError
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Tuple, List, Callable, TypeVar, Optional

from gi.repository import GObject, GLib

from settings import defaults
from device.device import DeviceAddress, Device, Cell, Controller
from device.registers import TemperatureSensor
from gui.gtk_util import glib_wait_future
from profile import DeviceProfile
from state import DeviceParameter, \
    CellState, CellUpdates, CellSettings, \
    read_cell_state, read_cell_updates, write_cell_settings, update_cell_state, \
    update_desired_state, update_actual_state, \
    ControllerState, ControllerUpdates, \
    read_controller_state, read_controller_updates, update_controller_state

T = TypeVar('T')

CHANNEL_COUNT = 16

SOCKET_TIMEOUT = 10

LOGGER = logging.getLogger('gui.worker')


def _read_device_updates(device: Device) -> Tuple[ControllerUpdates, List[CellUpdates]]:
    return read_controller_updates(device.controller), list(map(read_cell_updates, device.cells))


def _read_device_state(device: Device) -> Tuple[ControllerState, List[CellState]]:
    return read_controller_state(device.controller), list(map(read_cell_state, device.cells))


def _connect(executor: ThreadPoolExecutor, address: DeviceAddress) -> 'Worker':
    try:
        # Connect
        LOGGER.debug(f'Connecting to {address}')
        dev = Device(address, CHANNEL_COUNT, SOCKET_TIMEOUT)
        # Write defaults
        LOGGER.debug(f'Writing defaults to {address}')
        if defaults is None:
            LOGGER.warning(f'No default values')
        else:
            for r, v in defaults.controller.items():
                dev.controller.write(r, v)
            for cell in dev.cells:
                for r, v in defaults.cell.items():
                    cell.write(r, v)
        # Read state
        LOGGER.debug(f'Reading state from {address}')
        ctl, cells = _read_device_state(dev)
    except (EOFError, OSError) as e:
        msg = f'Failed to connect to {address}: {e}'
        LOGGER.error(msg)
        raise ConnectionError(msg)

    LOGGER.info(f'Connected to {address}')
    return Worker(executor, dev, ctl, cells)


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
    CONNECTION_ERROR = 'connection-error'

    def __init__(self, executor: ThreadPoolExecutor, device: Device,
                 ctl_state: ControllerState, cells_state: List[CellState]):
        """This method is for internal use only. Use Worker.create(address) instead."""
        super().__init__()
        self._executor = executor
        self._device = device
        self._state = cells_state
        self._controller_state = ctl_state
        self._shutdown = False
        GLib.timeout_add(10000, self._on_timer)

    @staticmethod
    def create(address: DeviceAddress) -> 'Future[Worker]':
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=str(address))
        return executor.submit(_connect, executor, address)

    def close(self) -> 'Future[None]':
        if self._executor is None:
            raise RuntimeError('Illegal worker state')

        future = self._executor.submit(self._device.close)
        self._shutdown = True
        self._executor.shutdown(wait=False)
        self._executor = None
        return future

    def get_device_address(self) -> DeviceAddress:
        return self._device.address

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

    def _cell_id(self, cell_index: int) -> str:
        return self._device.cells[cell_index - 1].name

    def _get_cell_and_state(self, cell_index):
        cell = self._device.cells[cell_index - 1]
        state = self._state[cell_index - 1]
        return cell, state

    def _submit_work(self, work, args, callback, cb_args):
        glib_wait_future(
            self._executor.submit(self._do_work, work, args),
            callback, *cb_args)

    def _do_work(self, work, args):
        if self._shutdown:
            raise CancelledError
        try:
            return work(*args)
        except (OSError, EOFError):
            self._shutdown = True
            raise

    def _handle_result(self, future: Future) -> bool:
        try:
            future.result()
            return True
        except CancelledError:
            LOGGER.warning(f'{self.get_device_address()}: Action cancelled')
        except (OSError, EOFError) as e:
            msg = f'{self.get_device_address()}: Connection error: {e}'
            LOGGER.error(msg)
            self.close()
            self.emit(Worker.CONNECTION_ERROR, msg)
        return False

    def _start_parameter_modification(self, cell_index: int, parameter: DeviceParameter[T],
                                      task: Callable[[Cell, T], T], value: T):
        LOGGER.debug(f'Starting modification of parameter of the cell {self._cell_id(cell_index)}. '
                     f'Value: {value}, Task: {task}')
        cell, state = self._get_cell_and_state(cell_index)

        parameter.set_desired_inc_waiting(value)
        self._submit_work(task, (cell, value), self._complete_parameter_modification, (state, parameter))
        self.emit(Worker.CELL_UPDATED, state.cell_index)

    def _complete_parameter_modification(self, f: Future, state: CellState, parameter: DeviceParameter):
        if not self._handle_result(f):
            return
        result = f.result()
        LOGGER.debug(f'Completing modification of parameter of the cell {self._cell_id(state.cell_index)}. '
                     f'Value: {result}')
        parameter.set_actual_dec_waiting(result)
        self.emit(Worker.CELL_UPDATED, state.cell_index)

    def _start_cell_modification(self, cell_index: int, settings: CellSettings):
        LOGGER.debug(f'Starting modification of the cell {self._cell_id(cell_index)}')
        cell, state = self._get_cell_and_state(cell_index)

        update_desired_state(state, settings)
        self._submit_work(write_cell_settings, (cell, settings), self._complete_cell_modification, (state,))
        self.emit(Worker.CELL_UPDATED, state.cell_index)

    def _complete_cell_modification(self, f: Future, state: CellState):
        if not self._handle_result(f):
            return
        settings = f.result()
        LOGGER.debug(f'Completing modification of the cell {self._cell_id(state.cell_index)}')
        update_actual_state(state, settings)
        self.emit(Worker.CELL_UPDATED, state.cell_index)

    def _start_ctl_modification(self, parameter: DeviceParameter[T], task: Callable[[Controller, T], T], value: T):
        LOGGER.debug(f'Starting controller parameter modification. Value: {value}')
        parameter.set_desired_inc_waiting(value)
        self._submit_work(task, (self._device.controller, value), self._complete_ctl_modification, (parameter,))
        self.emit(Worker.CONTROLLER_UPDATED)

    def _complete_ctl_modification(self, f: Future, parameter: DeviceParameter):
        if not self._handle_result(f):
            return
        result = f.result()
        LOGGER.debug(f'Completing controller parameter modification. Value: {result}')
        parameter.set_actual_dec_waiting(result)
        self.emit(Worker.CONTROLLER_UPDATED)

    def _start_update(self):
        LOGGER.debug(f'Start reading values. Device: {self.get_device_address()}')
        glib_wait_future(self._executor.submit(_read_device_updates, self._device),
                         self._complete_update)

    def _complete_update(self, f: 'Future[Tuple[ControllerUpdates, List[CellUpdates]]]'):
        if not self._handle_result(f):
            return
        ctl_updates, cell_updates = f.result()
        LOGGER.debug(f'Completion of reading values. Device: {self.get_device_address()}')
        update_controller_state(self._controller_state, ctl_updates)
        self.emit(Worker.CONTROLLER_UPDATED)
        for state, updates in zip(self._state, cell_updates):
            update_cell_state(state, updates)
            self.emit(Worker.CELL_UPDATED, state.cell_index)
        self.emit(Worker.UPDATED)

    def set_enabled(self, cell_index: int, value: bool):
        state = self.get_cell_state(cell_index)
        self._start_parameter_modification(cell_index, state.enabled, Cell.set_output_voltage_enabled, bool(value))

    def set_output_voltage(self, cell_index: int, value: float):
        state = self.get_cell_state(cell_index)
        check_voltage_value(state, value)
        self._start_parameter_modification(cell_index, state.voltage_set, Cell.set_output_voltage, value)

    def set_current_limit(self, cell_index: int, value: float):
        state = self.get_cell_state(cell_index)
        check_current_value(state, value)
        self._start_parameter_modification(cell_index, state.current_limit, Cell.set_current_limit, value)

    def set_ramp_up_speed(self, cell_index: int, value: int):
        state = self.get_cell_state(cell_index)
        check_ramp_up_value(state, value)
        self._start_parameter_modification(cell_index, state.ramp_up_speed, Cell.set_ramp_up_speed, value)

    def set_ramp_down_speed(self, cell_index: int, value: int):
        state = self.get_cell_state(cell_index)
        check_ramp_down_value(state, value)
        self._start_parameter_modification(cell_index, state.ramp_down_speed, Cell.set_ramp_down_speed, value)

    def load_device_profile(self, profile: DeviceProfile) -> None:
        """
        Set parameters of all device channels.

        :param profile: Contains settings for cells. Cells that are not listed are disabled.

        :raises IndexError: the voltage cell with specified index does not exist.
        :raises ValueError: when some values are invalid.
        """

        # Check values and restore order
        new_values: List[Optional[CellSettings]] = [None] * len(self._state)
        for cell_index, settings in profile.cell_settings.items():
            state = self.get_cell_state(cell_index)
            check_voltage_value(state, settings.voltage_set)
            check_current_value(state, settings.current_limit)
            check_ramp_up_value(state, settings.ramp_up_speed)
            check_ramp_down_value(state, settings.ramp_down_speed)
            new_values[cell_index - 1] = settings

        # Set desired values and start modification
        for cell, settings in zip(self._state, new_values):
            if settings is None:
                self.set_enabled(cell.cell_index, False)
            else:
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

    @GObject.Signal(name=CONNECTION_ERROR)
    def _on_connection_error(self, msg: str):
        pass

    def _on_timer(self):
        if self._shutdown:
            return False
        self._start_update()
        return True

    def __str__(self):
        return f'<Worker {self._device.address}>'
