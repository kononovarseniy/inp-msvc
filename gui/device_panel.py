import logging
from enum import IntEnum
from typing import TypeVar, Callable, Any

from gi.repository import Gtk

from gui.error_label import ErrorLabel
from gui.treeview_helpers import TreeModelAdapter, get_row_being_edited
from gui.worker import CellState, DeviceParameter, Worker

LOGGER = logging.getLogger('device-panel')
T = TypeVar('T')


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


def make_parameter_data_func(get: Callable[[CellState], DeviceParameter]):
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

    def __init__(self, worker: Worker):
        super().__init__()

        self.worker = worker
        self.worker.connect(Worker.CELL_UPDATED, self._on_cell_updated)

        grid = Gtk.Grid()
        grid.set_column_spacing(4)
        grid.set_row_spacing(4)

        device_label = Gtk.Label()
        device_label.set_xalign(0)
        device_label.set_markup(f'Connected to <b>{self.worker.get_device_address()}</b>')
        grid.attach(device_label, 0, 0, 1, 1)

        self.error_label = ErrorLabel()
        grid.attach(self.error_label, 1, 0, 1, 1)

        self.tree_view, self.adapter = self._make_tree_view()
        grid.attach(self.tree_view, 0, 1, 2, 1)

        for cell in self.worker.iter_cells():
            self.adapter.append(cell)

        self.add(grid)

    def _make_on_changed(self, task):
        def on_changed(state: CellState, value: Any):
            try:
                task(self.worker, state.cell_index, value)
            except ValueError as e:
                LOGGER.debug(f'User entered an invalid value: {e}')
                self.error_label.show_error(str(e))

        return on_changed

    def _make_tree_view(self):
        adapter = TreeModelAdapter()
        tree_view = Gtk.TreeView(model=adapter.model)

        adapter.append_text_column(tree_view, '#',
                                   make_simple_text_data_func(lambda s: str(s.cell_index)))

        adapter.append_toggle_column(tree_view, 'Enabled', cell_enabled_data_func,
                                     self._make_on_changed(Worker.set_enabled))

        adapter.append_text_column(tree_view, 'Voltage, V\n(desired)',
                                   make_parameter_data_func(lambda s: s.voltage_set),
                                   float, self._make_on_changed(Worker.set_output_voltage))

        adapter.append_text_column(tree_view, 'Voltage, V\n(set)',
                                   make_simple_text_data_func(lambda s: f'{s.voltage_set.actual:.0f}'))

        adapter.append_text_column(tree_view, 'Voltage, V\n(measured)', measured_voltage_data_func)

        adapter.append_text_column(tree_view, 'Measured\ncurrent, uA', measured_current_data_func)

        adapter.append_text_column(tree_view, 'Current\nlimit, uA',
                                   make_parameter_data_func(lambda s: s.current_limit),
                                   float, self._make_on_changed(Worker.set_current_limit))

        adapter.append_text_column(tree_view, 'Ramp\nup, V/s',
                                   make_parameter_data_func(lambda s: s.ramp_up_speed),
                                   int, self._make_on_changed(Worker.set_ramp_up_speed))

        adapter.append_text_column(tree_view, 'Ramp\ndown, V/s',
                                   make_parameter_data_func(lambda s: s.ramp_down_speed),
                                   int, self._make_on_changed(Worker.set_ramp_down_speed))

        adapter.append_text_column(tree_view, 'Voltage\nrange, V', voltage_range_data_func)
        adapter.append_text_column(tree_view, 'Current limit\nrange, uA', current_limit_range_data_func)

        return tree_view, adapter

    def _update_row(self, index: int):
        path = get_row_being_edited(self.tree_view)
        row = path.get_indices()[0] if path is not None else None
        if index != row:
            self.adapter.row_changed(index)

    def _on_cell_updated(self, _: Worker, index: int) -> None:
        self._update_row(index - 1)

    def stop(self):
        if self.worker is None:
            raise RuntimeError('Illegal state')

        LOGGER.debug(f'Stopping device panel {self.worker.get_device_address()})')
        self.adapter.clear()
        f = self.worker.close()
        self.worker = None
        return f
