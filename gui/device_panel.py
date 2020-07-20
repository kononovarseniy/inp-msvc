import logging
from concurrent.futures import Future
from dataclasses import dataclass
from enum import IntEnum
from typing import TypeVar, Generic, Tuple, Callable, List, Optional

from gi.repository import Gtk, GLib, GObject

from device.worker import CellState as RealCellState, DeviceAddress, DeviceState, Worker
from gui.treeview_helpers import TreeModelAdapter, get_row_being_edited

LOGGER = logging.getLogger('device-panel')
T = TypeVar('T')


class SlowVar(Generic[T]):
    def __init__(self, desired: T, actual: T = None, waiting: bool = False):
        self.desired = desired
        self.actual = actual if actual is not None else desired
        self.waiting = waiting

    def update_value(self, value: T) -> None:
        self.actual = value
        if not self.waiting:
            self.desired = value


@dataclass
class CellState:
    enabled: SlowVar[bool]
    voltage_set: SlowVar[float]
    current_limit: SlowVar[float]
    ramp_up_speed: SlowVar[int]
    ramp_down_speed: SlowVar[int]

    # Readonly values
    voltage_measured: float
    current_measured: float

    # Constant values
    cell_index: int
    voltage_range: Tuple[float, float]
    current_limit_range: Tuple[float, float]

    @staticmethod
    def from_real_state(state: RealCellState) -> 'CellState':
        return CellState(
            SlowVar(state.enabled),
            SlowVar(state.voltage_set),
            SlowVar(state.current_limit),
            SlowVar(state.ramp_up),
            SlowVar(state.ramp_down),
            state.voltage_measured,
            state.current_measured,
            state.index,
            state.output_voltage_range,
            state.current_limit_range
        )

    def fetch_actual_values(self, state: RealCellState) -> None:
        self.enabled.update_value(state.enabled)
        self.voltage_set.update_value(state.voltage_set)
        self.current_limit.update_value(state.current_limit)
        self.ramp_up_speed.update_value(state.ramp_up)
        self.ramp_down_speed.update_value(state.ramp_down)
        self.voltage_measured = state.voltage_measured
        self.current_measured = state.current_measured
        # Do not fetch constant values


def render_cell(cell: Gtk.CellRenderer, text: str, state: str, editable: bool):
    if state == 'ok':
        cell.props.markup = text
        cell.props.cell_background = 'white' if editable else 'light gray'
    elif state == 'warning':
        cell.props.markup = f'<span background="yellow" foreground="black">{text}</span>'
        cell.props.cell_background = 'yellow'
    elif state == 'error':
        cell.props.markup = f'<span background="red" foreground="white" weight="bold">{text}</span>'
        cell.props.cell_background = 'red'


def make_simple_text_data_func(get: Callable[[CellState], str]):
    def wrapper(cell: Gtk.CellRenderer, state: CellState):
        cell.props.text = get(state)

    return wrapper


def make_slow_var_data_func(get: Callable[[CellState], SlowVar]):
    def data_func(cell: Gtk.CellRendererText, state: CellState):
        var = get(state)
        render_cell(cell, f'{var.desired:.0f}', 'warning' if var.waiting else 'ok', True)

    return data_func


def cell_enabled_data_func(cell: Gtk.CellRendererToggle, state: CellState):
    cell.props.active = state.enabled.desired
    cell.props.cell_background = 'yellow' if state.enabled.waiting else 'white'


def measured_voltage_data_func(cell: Gtk.CellRenderer, state: CellState):
    v_set = state.voltage_set.actual
    v_mes = state.voltage_measured
    en = state.enabled.actual

    if en:
        bad = abs(v_set - v_mes) >= 1
    else:
        bad = v_mes > 5

    render_cell(cell, f'{v_mes:.2f}', 'error' if bad else 'ok', False)


def measured_current_data_func(cell: Gtk.CellRenderer, state: CellState):
    i_lim = state.current_limit.actual
    i_mes = state.current_measured

    bad = i_mes > i_lim
    render_cell(cell, f'{i_mes:.2f}', 'error' if bad else 'ok', False)


def voltage_range_data_func(cell: Gtk.CellRendererText, state: CellState):
    l, h = state.voltage_range
    cell.props.text = f'{l:d}..{h:d}'


def current_limit_range_data_func(cell: Gtk.CellRendererText, state: CellState):
    l, h = state.current_limit_range
    cell.props.text = f'{l:d}..{h:d}'


class _State(IntEnum):
    STOPPING = 0
    STOPPED = 1
    STARTING = 2
    ERROR = 3
    STARTED = 4


class DevicePanel(Gtk.Box):

    def __init__(self):
        super().__init__()

        self.cells: List[CellState] = []
        self.device: Optional[DeviceAddress] = None
        self.worker: Optional[Worker] = None
        self._state = _State.STOPPED

        self.tree_view, self.adapter = self._make_tree_view()
        grid = Gtk.Grid()
        grid.attach(self.tree_view, 0, 0, 1, 1)
        self.add(grid)

    def is_connected(self):
        return self._state == _State.STARTED

    def start(self, device: DeviceAddress):
        if self._state != _State.STOPPED:
            raise RuntimeError('Illegal state')

        LOGGER.debug(f'Starting device panel ({device})')
        self._state = _State.STARTING
        self.device = device
        self.worker = Worker()
        self.worker.connect(device).add_done_callback(lambda f: GLib.idle_add(self._on_started, f))

    def _on_started(self, f: Future):
        e = f.exception()
        if e:
            LOGGER.error(f'Connection to {self.device} failed: {e}')
            self._state = _State.ERROR
            self.stop()
        else:
            LOGGER.debug(f'Connection to {self.device} established')
            self._state = _State.STARTED
            self.emit('started')

    @GObject.Signal
    def started(self):
        LOGGER.debug(f"Signal 'started' is emitted for {self.device}")

    def stop(self):
        if self._state <= _State.STARTING:
            raise RuntimeError('Illegal state')

        LOGGER.debug(f'Stopping device panel {self.device})')
        self._state = _State.STOPPING
        self.worker.shutdown().add_done_callback(lambda _: GLib.idle_add(self._on_stopped))

    def _on_stopped(self):
        self._state = _State.STOPPED
        LOGGER.debug(f"Emitting signal 'stopped' for {self.device}")
        self.device = None
        self.worker = None
        self.cells = []
        self.adapter.clear()
        self.emit('stopped')

    @GObject.Signal
    def stopped(self):
        pass

    def _make_tree_view(self):
        adapter = TreeModelAdapter()
        tree_view = Gtk.TreeView(model=adapter.model)

        adapter.append_text_column(tree_view, '#',
                                   make_simple_text_data_func(lambda s: str(s.cell_index)))

        adapter.append_toggle_column(tree_view, 'Enabled', cell_enabled_data_func,
                                     self.make_on_slow_var_changed(lambda s: s.enabled, Worker.set_output_enabled))

        adapter.append_text_column(tree_view, 'Voltage, V\n(desired)',
                                   make_slow_var_data_func(lambda s: s.voltage_set),
                                   float,
                                   self.make_on_slow_var_changed(lambda s: s.voltage_set, Worker.set_voltage))

        adapter.append_text_column(tree_view, 'Voltage, V\n(set)',
                                   make_simple_text_data_func(lambda s: f'{s.voltage_set.actual:.0f}'))

        adapter.append_text_column(tree_view, 'Voltage, V\n(measured)', measured_voltage_data_func)

        adapter.append_text_column(tree_view, 'Measured\ncurrent, uA', measured_current_data_func)

        adapter.append_text_column(tree_view, 'Current\nlimit, uA',
                                   make_slow_var_data_func(lambda s: s.current_limit),
                                   float, self.make_on_slow_var_changed(lambda s: s.current_limit,
                                                                        Worker.set_current_limit))

        adapter.append_text_column(tree_view, 'Ramp\nup, V/s',
                                   make_slow_var_data_func(lambda s: s.ramp_up_speed),
                                   int, self.make_on_slow_var_changed(lambda s: s.ramp_up_speed,
                                                                      Worker.set_ramp_up_speed))

        adapter.append_text_column(tree_view, 'Ramp\ndown, V/s',
                                   make_slow_var_data_func(lambda s: s.ramp_down_speed),
                                   int, self.make_on_slow_var_changed(lambda s: s.ramp_down_speed,
                                                                      Worker.set_ramp_down_speed))

        adapter.append_text_column(tree_view, 'Voltage\nrange, V', voltage_range_data_func)
        adapter.append_text_column(tree_view, 'Current limit\nrange, uA', current_limit_range_data_func)

        return tree_view, adapter

    def append_row(self, row: CellState):
        self.adapter.append(row)

    def update_row(self, index: int):
        self.adapter[index] = self.cells[index]

    def make_on_slow_var_changed(self, get: Callable[[CellState], SlowVar], do_work):
        def handler(state: CellState, value) -> bool:
            cell_index = state.cell_index - 1
            var = get(state)
            var.desired = value
            var.waiting = True
            do_work(self.worker, cell_index, value).add_done_callback(lambda f: done(f, cell_index))

            return True

        def done(f: Future, cell_index: int):
            res = f.result()

            state = self.cells[cell_index]
            var = get(state)

            var.waiting = False
            var.desired = res
            var.actual = res

            self.update_row(cell_index)

        return handler

    def on_state_read(self, f: 'Future[DeviceState]') -> None:
        result = f.result()
        full_update = len(self.adapter) != len(result.cells)

        preserve_row = None
        if full_update:
            self.adapter.clear()
            self.cells = [CellState.from_real_state(s) for s in result.cells]
        else:
            path = get_row_being_edited(self.tree_view)
            if path:
                preserve_row = path.get_indices()[0]

            for state, actual in zip(self.cells, result.cells):
                state.fetch_actual_values(actual)

        for i, state in enumerate(self.cells):
            if full_update:
                self.append_row(state)
            elif i != preserve_row:
                self.update_row(i)
        LOGGER.debug(f'Values for device {self.device} are updated')

    def start_update(self):
        LOGGER.debug(f'Updating values for device {self.device}')
        self.worker.read_state() \
            .add_done_callback(lambda f: GLib.idle_add(self.on_state_read, f))
