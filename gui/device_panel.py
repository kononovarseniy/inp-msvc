import logging
from typing import TypeVar, Callable, Any, Iterable, Optional

from gi.repository import Gtk, Gdk, GObject

from gui.error_label import ErrorLabel
from gui.treeview_helpers import TreeModelAdapter, get_row_being_edited
from gui.worker import Worker
from gui.state import CellState, DeviceParameter

STATUS_HELP_TEXT = """* Errors:
\tE\tUnknown
\tI\tCurrent overload
\tB\tBase voltage error
\tH\tHardware failure
\tS\tStandby regime\n\t\t(current limiting)
\tP\tI/O Protection active"""

LOGGER = logging.getLogger('device-panel')
T = TypeVar('T')


def warning_markup(text: Any) -> str:
    return f'<span background="yellow" foreground="black">{text}</span>'


def error_markup(text: Any) -> str:
    return f'<span background="red" foreground="white" weight="bold">{text}</span>'


def good_markup(text: Any) -> str:
    return f'<span background="green" foreground="white" weight="bold">{text}</span>'


def make_markup(state: str, text: Any) -> str:
    if state == 'ok':
        return str(text)
    elif state == 'warning':
        return warning_markup(text)
    elif state == 'error':
        return error_markup(text)
    elif state == 'good':
        return good_markup(text)


def render_cell(cell: Gtk.CellRenderer, text: Any, state: str, editable: bool):
    cell.props.markup = make_markup(state, text)

    if state == 'ok':
        cell.props.cell_background = 'white' if editable else 'light gray'
    elif state == 'warning':
        cell.props.cell_background = 'yellow'
    elif state == 'error':
        cell.props.cell_background = 'red'
    elif state == 'good':
        cell.props.cell_background = 'green'


def cell_index_data_func(cell: Gtk.CellRenderer, state: CellState):
    render_cell(cell, state.cell_index, 'good' if state.enabled.actual else 'ok', False)


def make_parameter_data_func(get: Callable[[CellState], DeviceParameter]):
    def data_func(cell: Gtk.CellRendererText, state: CellState):
        var = get(state)
        render_cell(cell, f'{var.desired:.0f}', 'warning' if var.waiting else 'ok', True)

    return data_func


def cell_enabled_data_func(cell: Gtk.CellRendererToggle, state: CellState):
    cell.props.active = state.enabled.desired
    if state.enabled.waiting:
        cell.props.cell_background = 'yellow'
    elif state.auto_enable:
        cell.props.cell_background = 'white'
    else:
        cell.props.cell_background = 'light gray'


def measured_voltage_data_func(cell: Gtk.CellRenderer, state: CellState):
    v_set = state.voltage_set.actual
    v_mes = state.voltage_measured
    up = state.csr.ramp_up_active
    down = state.csr.ramp_down_active
    en = state.enabled.actual

    if en:
        bad = abs(v_set - v_mes) >= 1
    else:
        bad = v_mes > 5

    slope = ''
    if up:
        slope = '↑ '
    if down:
        slope = '↓ '

    render_cell(cell, f'<b>{slope}</b>{v_mes:.2f}', 'error' if bad else 'ok', False)


def voltage_set_data_func(cell: Gtk.CellRenderer, state: CellState):
    cell.props.text = f'{state.voltage_set.actual:.0f}'


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


def cell_status_data_func(cell: Gtk.CellRendererText, state: CellState):
    err = False
    msg = ''
    if state.csr.error:
        msg += 'E'
    if state.csr.current_overload:
        msg += 'I'
        err = True
    if state.csr.base_voltage_error:
        msg += 'B'
        err = True
    if state.csr.hardware_failure_error:
        msg += 'H'
        err = True
    if state.csr.standby:
        msg += 'S'
        err = True
    if state.csr.io_protection:
        msg += 'P'
        err = True

    render_cell(cell, msg if msg else '\u2014', 'error' if err else 'ok', False)


class NumberEntry(Gtk.Entry, Gtk.Editable):
    def __init__(self):
        super().__init__()

    def do_insert_text(self, new_text, length, position):
        if all(c.isdigit() for c in new_text):
            self.get_buffer().insert_text(position, new_text, length)
            return position + len(new_text)
        else:
            return position


class ParamLabel(Gtk.Label):
    def __init__(self, label_text: str):
        super().__init__()

        self._text = label_text
        self._state = 'ok'
        self._empty = True

        self.set_markup(self._text)
        self.set_xalign(1)

    def set_text(self, text: str):
        self._text = text
        self._update()

    def set_state(self, state: str):
        self._state = state
        self._update()

    def _update(self):
        self.set_markup(make_markup(self._state, self._text))


class TempEditor(GObject.Object):
    def __init__(self, grid: Gtk.Grid, label_text: str, x: int, y: int):
        super().__init__()

        self._empty = True

        self.label = ParamLabel(label_text)
        grid.attach(self.label, x, y, 1, 1)

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
        self.label.set_state('warning' if param.waiting else 'ok')


class DevicePanel(Gtk.Box):
    worker: Optional[Worker]

    def __init__(self, worker: Worker):
        super().__init__()

        self.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA.from_color(Gdk.color_parse('white')))

        grid = Gtk.Grid()
        grid.set_column_spacing(4)
        grid.set_row_spacing(4)
        grid.set_margin_top(4)
        grid.set_margin_left(4)
        grid.set_margin_right(4)

        self.device_label = Gtk.Label()
        self.device_label.set_xalign(0)
        grid.attach(self.device_label, 0, 0, 1, 1)

        self.error_label = ErrorLabel()
        self.error_label.set_xalign(1)
        grid.attach(self.error_label, 1, 0, 1, 1)

        self.tree_view, self.adapter = self._make_tree_view()
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        scroll.add(self.tree_view)
        frame = Gtk.Frame()
        frame.set_hexpand(True)
        frame.add(scroll)
        grid.attach(frame, 0, 1, 2, 1)

        status_help = Gtk.Label(label=STATUS_HELP_TEXT)
        status_help.set_xalign(0)

        dashboard, self._on_controller_updated = self._make_controller_dashboard()
        align = Gtk.Alignment(xalign=0)
        align.add(dashboard)
        box = Gtk.Box()
        box.set_orientation(Gtk.Orientation.HORIZONTAL)
        box.pack_start(align, False, True, 0)
        box.pack_start(status_help, False, False, 0)
        grid.attach(box, 0, 2, 2, 1)

        self.set_worker(worker)

        self.add(grid)

    def stop(self):
        if self.worker is None:
            raise RuntimeError('Illegal state')

        LOGGER.debug(f'Stopping device panel {self.worker.get_device_address()})')
        self.adapter.clear()
        f = self.worker.close()
        self.worker = None
        return f

    def set_worker(self, worker: Worker) -> None:
        self.worker = worker

        # Update components
        self.adapter.clear()
        for cell in self.worker.iter_cells():
            self.adapter.append(cell)
        self._on_controller_updated(worker)
        self.device_label.set_markup(f'Connected to <b>{self.worker.get_device_address()}</b>')

        self.worker.connect(Worker.CELL_UPDATED, self._on_cell_updated)
        self.worker.connect(Worker.CONTROLLER_UPDATED, self._on_controller_updated)

    def _make_on_changed(self, task):
        def on_changed(state: CellState, value: Any) -> bool:
            try:
                task(self.worker, state.cell_index, value)
                return True
            except ValueError as e:
                LOGGER.debug(f'User entered an invalid value: {e}')
                self.error_label.show_error(str(e))
                return False

        return on_changed

    def _make_tree_view(self):
        adapter = TreeModelAdapter()
        tree_view = Gtk.TreeView(model=adapter.model)

        adapter.append_text_column(tree_view, '#', cell_index_data_func)

        adapter.append_toggle_column(tree_view, 'En.\n(des)', cell_enabled_data_func,
                                     self._make_on_changed(Worker.set_enabled))

        adapter.append_text_column(tree_view, 'Voltage, V\n(desired)',
                                   make_parameter_data_func(lambda s: s.voltage_set),
                                   float, self._make_on_changed(Worker.set_output_voltage))

        adapter.append_text_column(tree_view, 'Voltage, V\n(set)', voltage_set_data_func)

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

        adapter.append_text_column(tree_view, 'Errors\n*', cell_status_data_func)
        adapter.append_text_column(tree_view, 'Voltage\nrange, V', voltage_range_data_func)
        adapter.append_text_column(tree_view, 'Current limit\nrange, uA', current_limit_range_data_func)

        return tree_view, adapter

    def _make_controller_dashboard(self) -> (Gtk.Widget, Callable[[Worker], None]):
        grid = Gtk.Grid()
        grid.set_row_spacing(4)
        grid.set_column_spacing(4)
        grid.set_hexpand(True)

        def attach_with_label(label_str: str, x: int, y: int, *args: Iterable[Gtk.Widget]) -> ParamLabel:
            label = ParamLabel(label_str)
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

        state_label = ParamLabel('state:')
        grid.attach(state_label, 1, 3, 1, 1)
        state_text = ParamLabel('')
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
                state_text.set_text(', '.join(msg))
                state_text.set_state('error')
            else:
                state_text.set_text('OK')
                state_text.set_state('good')

        return grid, update_all

    def _update_row(self, index: int):
        path = get_row_being_edited(self.tree_view)
        row = path.get_indices()[0] if path is not None else None
        if index != row:
            self.adapter.row_changed(index)

    def _on_cell_updated(self, _: Worker, index: int) -> None:
        self._update_row(index - 1)

    def _on_enable_all(self, button):
        for i in range(1, self.worker.get_cell_count() + 1):
            state = self.worker.get_cell_state(i)
            if state.auto_enable:
                self.worker.set_enabled(i, True)

    def _on_disable_all(self, button):
        for i in range(1, self.worker.get_cell_count() + 1):
            self.worker.set_enabled(i, False)
