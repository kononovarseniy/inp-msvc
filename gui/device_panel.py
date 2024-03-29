import logging
from typing import Tuple, TypeVar, Callable, Any, Iterable, Optional

from gi.repository import Gtk, Gdk, GObject

import checks
from checks import ErrorType
from gui.markup import make_markup, render_cell
from gui.gtk_util import NumberEntry, get_row_being_edited, TreeModelAdapter
from gui.widgets.error_label import create_error_label
from observable import Observable
from gui.widgets.profile_label import create_profile_label
from gui.widgets.status_label import create_status_label
from gui.worker import Worker
from profile import Profile
from state import CellState, DeviceParameter

STATUS_HELP_TEXT = """* Errors:
\tE\tUnknown
\tI\tCurrent overload
\tB\tBase voltage error
\tH\tHardware failure
\tS\tStandby regime\n\t\t(current limiting)
\tP\tI/O Protection active"""

LOGGER = logging.getLogger('device-panel')
T = TypeVar('T')


def make_parameter_data_func(get: Callable[[CellState], DeviceParameter]):
    def data_func(cell: Gtk.CellRendererText, state: CellState):
        var = get(state)
        render_cell(cell, f'{var.desired:.0f}', ErrorType.warning if var.waiting else ErrorType.ok, True)

    return data_func


def make_format_data_func(fmt: Callable[[CellState], str], check: Callable[[CellState], ErrorType]):
    return lambda cell, state: render_cell(cell, fmt(state), check(state), False)


def format_cell_index(state: CellState) -> str:
    return str(state.cell_index)


def format_counter_number(state: CellState) -> str:
    return state.counter_number


def cell_enabled_data_func(cell: Gtk.CellRendererToggle, state: CellState):
    cell.props.active = state.enabled.desired
    if state.enabled.waiting:
        cell.props.cell_background = 'yellow'
    elif state.auto_enable:
        cell.props.cell_background = 'white'
    else:
        cell.props.cell_background = 'light gray'


def format_voltage_set(state: CellState) -> str:
    return f'{state.voltage_set.actual:.0f}'


def format_measured_voltage(state: CellState) -> str:
    slope = ''
    if state.csr.ramp_up_active:
        slope = '↑ '
    if state.csr.ramp_down_active:
        slope = '↓ '
    return f'<b>{slope}</b>{state.voltage_measured:.2f}'


def format_measured_current(state: CellState):
    return f'{state.current_measured:.2f}'


def format_cell_status(state: CellState) -> str:
    res = ''
    if state.csr.error:
        res += 'E'
    if state.csr.current_overload:
        res += 'I'
    if state.csr.base_voltage_error:
        res += 'B'
    if state.csr.hardware_failure_error:
        res += 'H'
    if state.csr.standby:
        res += 'S'
    if state.csr.io_protection:
        res += 'P'

    return res if res else '\u2014'


def voltage_range_data_func(cell: Gtk.CellRendererText, state: CellState):
    l, h = state.voltage_range
    cell.props.text = f'{l:d}..{h:d}'
    cell.props.cell_background = 'light gray'


def current_limit_range_data_func(cell: Gtk.CellRendererText, state: CellState):
    l, h = state.current_limit_range
    cell.props.text = f'{l:d}..{h:d}'
    cell.props.cell_background = 'light gray'


class TempEditor(GObject.Object):
    def __init__(self, grid: Gtk.Grid, label_text: str, x: int, y: int):
        super().__init__()

        self._empty = True

        self.state = Observable(ErrorType.ok)
        label = create_status_label(label_text, self.state)
        label.set_xalign(1)
        grid.attach(label, x, y, 1, 1)

        self.desired = NumberEntry()
        self.desired.set_width_chars(4)
        self.desired.set_max_length(4)

        def on_enter(entry: Gtk.Entry):
            val = int(entry.get_text())
            entry.set_text(str(val))
            self.emit('completed', val)

        self.desired.connect('activate', on_enter)
        grid.attach(self.desired, x + 1, y, 1, 1)

        self.actual = Gtk.Entry()
        self.actual.set_sensitive(False)
        self.actual.set_width_chars(4)
        grid.attach(self.actual, x + 2, y, 1, 1)

    @GObject.Signal(name='completed')
    def _on_completed(self, value: int):
        pass

    def update(self, param: DeviceParameter[int]):
        if self._empty:
            self.desired.set_text(f'{param.desired}')
            self._empty = False
        self.actual.set_text(f'{param.actual} \u00B0C')
        self.state.value = checks.check_parameter(param)


class DevicePanel(Gtk.Box):
    worker: Optional[Worker]

    def __init__(self, worker: Worker, profile: Observable[Optional[Profile]]):
        super().__init__()

        self.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA.from_color(Gdk.color_parse('white')))

        self._error_text = Observable('')

        grid = Gtk.Grid()
        grid.set_column_spacing(4)
        grid.set_row_spacing(4)
        grid.set_margin_top(4)
        grid.set_margin_left(4)
        grid.set_margin_right(4)

        self.device_label = Gtk.Label()
        self.device_label.set_xalign(0)
        grid.attach(self.device_label, 0, 0, 1, 1)

        error_label = create_error_label(self._error_text)
        error_label.set_xalign(1)
        grid.attach(error_label, 1, 0, 1, 1)

        profile_label = create_profile_label(profile)
        profile_label.set_xalign(0)
        grid.attach(profile_label, 0, 1, 2, 1)

        self.tree_view, self.adapter = self._make_tree_view()
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        scroll.add(self.tree_view)
        frame = Gtk.Frame()
        frame.set_hexpand(True)
        frame.add(scroll)
        grid.attach(frame, 0, 2, 2, 1)

        status_help = Gtk.Label(label=STATUS_HELP_TEXT)
        status_help.set_xalign(0)

        dashboard, self._on_controller_updated = self._make_controller_dashboard()
        align = Gtk.Alignment(xalign=0)
        align.add(dashboard)
        box = Gtk.Box()
        box.set_orientation(Gtk.Orientation.HORIZONTAL)
        box.pack_start(align, False, True, 0)
        box.pack_start(status_help, False, False, 0)
        grid.attach(box, 0, 3, 2, 1)

        self.worker = worker
        self.worker.connect(Worker.CELL_UPDATED, self._on_cell_updated)
        self.worker.connect(Worker.CONTROLLER_UPDATED, self._on_controller_updated)

        # Update components
        self.adapter.clear()
        for cell in self.worker.iter_cells():
            self.adapter.append(cell)
        self._on_controller_updated(worker)
        self.device_label.set_markup(f'Connected to <b>{self.worker.get_device_address()}</b>')

        self.add(grid)

    def stop(self):
        if self.worker is None:
            raise RuntimeError('Illegal state')

        LOGGER.debug(f'Stopping device panel {self.worker.get_device_address()})')
        self.adapter.clear()
        f = self.worker.close()
        self.worker = None
        return f

    def _make_on_changed(self, task):
        def on_changed(state: CellState, value: Any) -> bool:
            try:
                task(self.worker, state.cell_index, value)
                return True
            except ValueError as e:
                LOGGER.debug(f'User entered an invalid value: {e}')
                self._error_text.value = str(e)
                return False

        return on_changed

    def _make_tree_view(self):
        adapter = TreeModelAdapter()
        tree_view = Gtk.TreeView(model=adapter.model)

        adapter.append_text_column(tree_view, '#',
                                   make_format_data_func(format_cell_index, checks.good_if_output_enabled))

        adapter.append_text_column(tree_view, 'Cntr',
                                   make_format_data_func(format_counter_number, lambda _: ErrorType.ok))

        adapter.append_toggle_column(tree_view, 'En.\n(des)', cell_enabled_data_func,
                                     self._make_on_changed(Worker.set_enabled))

        adapter.append_text_column(tree_view, 'Voltage, V\n(desired)',
                                   make_parameter_data_func(lambda s: s.voltage_set),
                                   float, self._make_on_changed(Worker.set_output_voltage))

        adapter.append_text_column(tree_view, 'Voltage, V\n(set)',
                                   make_format_data_func(format_voltage_set, checks.check_actual_voltage_set))

        adapter.append_text_column(tree_view, 'Voltage, V\n(measured)',
                                   make_format_data_func(format_measured_voltage, checks.check_measured_voltage))

        adapter.append_text_column(tree_view, 'Measured\ncurrent, uA',
                                   make_format_data_func(format_measured_current, checks.check_measured_current))

        adapter.append_text_column(tree_view, 'Current\nlimit, uA',
                                   make_parameter_data_func(lambda s: s.current_limit),
                                   float, self._make_on_changed(Worker.set_current_limit))

        adapter.append_text_column(tree_view, 'Ramp\nup, V/s',
                                   make_parameter_data_func(lambda s: s.ramp_up_speed),
                                   int, self._make_on_changed(Worker.set_ramp_up_speed))

        adapter.append_text_column(tree_view, 'Ramp\ndown, V/s',
                                   make_parameter_data_func(lambda s: s.ramp_down_speed),
                                   int, self._make_on_changed(Worker.set_ramp_down_speed))

        adapter.append_text_column(tree_view, 'Errors\n*',
                                   make_format_data_func(format_cell_status, checks.check_cell_status))

        adapter.append_text_column(tree_view, 'Voltage\nrange, V', voltage_range_data_func)
        adapter.append_text_column(tree_view, 'Current limit\nrange, uA', current_limit_range_data_func)

        return tree_view, adapter

    def _make_controller_dashboard(self) -> Tuple[Gtk.Widget, Callable[[Worker], None]]:
        grid = Gtk.Grid()
        grid.set_row_spacing(4)
        grid.set_column_spacing(4)
        grid.set_hexpand(True)

        def attach_with_label(label_str: str, x: int, y: int, *args: Iterable[Gtk.Widget]) -> Gtk.Label:
            label = Gtk.Label(label=label_str)
            grid.attach(label, x, y, 1, 1)
            for i, w in enumerate(args):
                grid.attach(w, x + 1 + i, y, 1, 1)
            return label

        def attach_text_indicator(label_str: str, x: int, y: int) -> Gtk.Entry:
            text = Gtk.Entry()
            text.set_sensitive(False)
            text.set_width_chars(6)
            attach_with_label(label_str, x, y, text)
            return text

        enable_all_button = Gtk.Button(label='Enable all cells')
        enable_all_button.connect('clicked', self._on_enable_all)
        grid.attach(enable_all_button, 0, 0, 1, 1)
        disable_all_button = Gtk.Button(label='Disable all cells')
        disable_all_button.connect('clicked', self._on_disable_all)
        grid.attach(disable_all_button, 0, 1, 1, 1)

        lv_text = attach_text_indicator('Low voltage:', 1, 0)
        bv_text = attach_text_indicator('Base voltage:', 1, 1)
        t_proc_text = attach_text_indicator('T<sub>proc</sub>:', 1, 2)

        t_off = TempEditor(grid, 'T<sub>fan off</sub>:', 6, 0)
        t_off.connect('completed', lambda _, val: self.worker.set_fan_off_temp(val))
        t_on = TempEditor(grid, 'T<sub>fan on</sub>:', 6, 1)
        t_on.connect('completed', lambda _, val: self.worker.set_fan_on_temp(val))
        t_shutdown = TempEditor(grid, 'T<sub>shutdown</sub>:', 6, 2)
        t_shutdown.connect('completed', lambda _, val: self.worker.set_shutdown_temp(val))

        state_label = Gtk.Label(label='state:')
        state_label.set_xalign(1)
        grid.attach(state_label, 1, 3, 1, 1)
        state_text = Gtk.Label(label='')
        state_text.set_xalign(0)
        grid.attach(state_text, 2, 3, 6, 1)

        def update_all(worker: Worker):
            state = worker.get_controller_state()

            lv_text.set_text(f'{state.low_voltage:.1f} V')
            bv_text.set_text(f'{state.base_voltage:.1f} V')

            t_proc_text.set_text(f'{state.processor_temp} \u00B0C')

            t_off.update(state.fan_off_temp)
            t_on.update(state.fan_on_temp)
            t_shutdown.update(state.shutdown_temp)

            msg = []
            if state.status.temperature_protection:
                msg.append('T protection')
            if state.status.base_voltage_error:
                msg.append('BV error')
            if state.status.low_voltage_error:
                msg.append('LV error')
            if state.status.high_voltage_protection_active:
                msg.append('HV protection')
            if len(msg):
                state_text.set_markup(make_markup(ErrorType.error, ', '.join(msg)))
            else:
                state_text.set_markup(make_markup(ErrorType.good, 'OK'))

        return grid, update_all

    def _update_row(self, index: int):
        path = get_row_being_edited(self.tree_view)
        row = path.get_indices()[0] if path is not None else None
        if index != row:
            self.adapter.row_changed(index)

    def _on_cell_updated(self, _: Worker, index: int) -> None:
        self._update_row(index - 1)

    def _on_enable_all(self, _):
        for i in range(1, self.worker.get_cell_count() + 1):
            state = self.worker.get_cell_state(i)
            if state.auto_enable:
                self.worker.set_enabled(i, True)

    def _on_disable_all(self, _):
        for i in range(1, self.worker.get_cell_count() + 1):
            self.worker.set_enabled(i, False)
