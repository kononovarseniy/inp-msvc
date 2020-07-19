import logging
from concurrent.futures import Future
from dataclasses import dataclass
from typing import List, Callable, Tuple, Generic, TypeVar

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from device.worker import CellState as RealCellState
from device.worker import Worker, DeviceInfo, DeviceState
from gui.treeview_helpers import TreeModelAdapter, get_row_being_edited

logging.basicConfig(level=logging.NOTSET)
_log = logging.getLogger()

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


class MainWindow(Gtk.Window):

    def __init__(self):
        super().__init__()
        self.set_title('BINP muon system voltage controller')
        self.set_border_width(8)
        self.set_default_size(640, 480)

        self.cells: List[CellState] = []

        self.worker = Worker()
        self.worker.connect([DeviceInfo('dev1', ('127.0.0.1', 8080))]) \
            .add_done_callback(lambda f: GLib.timeout_add(1000, self.on_timer))

        self.tree_view, self.adapter = self.make_tree_view()

        # a grid to attach the widgets
        grid = Gtk.Grid()
        grid.attach(self.tree_view, 0, 0, 1, 1)

        # attach the grid to the window
        self.add(grid)

    def make_tree_view(self):
        adapter = TreeModelAdapter()
        tree_view = Gtk.TreeView(model=adapter.model)

        adapter.append_text_column(tree_view, '#',
                                   make_simple_text_data_func(lambda s: str(s.cell_index)))

        adapter.append_toggle_column(tree_view, 'Enabled', cell_enabled_data_func,
                                     self.make_on_slow_var_changed(lambda s: s.enabled, self.worker.set_output_enabled))

        adapter.append_text_column(tree_view, 'Voltage, V\n(desired)',
                                   make_slow_var_data_func(lambda s: s.voltage_set),
                                   float,
                                   self.make_on_slow_var_changed(lambda s: s.voltage_set, self.worker.set_voltage))

        adapter.append_text_column(tree_view, 'Voltage, V\n(set)',
                                   make_simple_text_data_func(lambda s: f'{s.voltage_set.actual:.0f}'))

        adapter.append_text_column(tree_view, 'Voltage, V\n(measured)', measured_voltage_data_func)

        adapter.append_text_column(tree_view, 'Measured\ncurrent, uA', measured_current_data_func)

        adapter.append_text_column(tree_view, 'Current\nlimit, uA',
                                   make_slow_var_data_func(lambda s: s.current_limit),
                                   float, self.make_on_slow_var_changed(lambda s: s.current_limit,
                                                                        self.worker.set_current_limit))

        adapter.append_text_column(tree_view, 'Ramp\nup, V/s',
                                   make_slow_var_data_func(lambda s: s.ramp_up_speed),
                                   int, self.make_on_slow_var_changed(lambda s: s.ramp_up_speed,
                                                                      self.worker.set_ramp_up_speed))

        adapter.append_text_column(tree_view, 'Ramp\ndown, V/s',
                                   make_slow_var_data_func(lambda s: s.ramp_down_speed),
                                   int, self.make_on_slow_var_changed(lambda s: s.ramp_down_speed,
                                                                      self.worker.set_ramp_down_speed))

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
            do_work(0, cell_index, value).add_done_callback(lambda f: done(f, cell_index))

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

    def on_state_read(self, f: 'Future[List[DeviceState]]') -> None:
        result = f.result()[0]  # Only for the first controller
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
        self.set_title('OK')

    def on_timer(self):
        self.set_title('READING')
        self.worker.read_state() \
            .add_done_callback(lambda f: GLib.idle_add(self.on_state_read, f))

        return True


if __name__ == '__main__':
    try:
        win = MainWindow()
        win.connect("destroy", Gtk.main_quit)
        win.show_all()
        Gtk.main()
    except KeyboardInterrupt:
        _log.warning('Process interrupted')
