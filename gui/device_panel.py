import logging
from typing import TypeVar, Callable, Any, Iterable

from gi.repository import Gtk, Gdk, GObject

from device.registers import TemperatureSensor
from gui.error_label import ErrorLabel
from gui.treeview_helpers import TreeModelAdapter, get_row_being_edited
from gui.worker import CellState, DeviceParameter, Worker

STATUS_HELP_TEXT = """* Errors:
\tE\tError
\tI\tCurrent overload
\tB\tBase voltage error
\tH\tHardware failure
\tS\tStandby regime\n\t\t(current limiting)
\tP\tI/O Protection active"""

LOGGER = logging.getLogger('device-panel')
T = TypeVar('T')


def warning_markup(text: str) -> str:
    return f'<span background="yellow" foreground="black">{text}</span>'


def error_markup(text: str) -> str:
    return f'<span background="red" foreground="white" weight="bold">{text}</span>'


def ok_markup(text: str) -> str:
    return f'<span background="green" foreground="white" weight="bold">{text}</span>'


def render_cell(cell: Gtk.CellRenderer, text: str, state: str, editable: bool):
    if state == 'ok':
        cell.props.markup = text
        cell.props.cell_background = 'white' if editable else 'light gray'
    elif state == 'warning':
        cell.props.markup = warning_markup(text)
        cell.props.cell_background = 'yellow'
    elif state == 'error':
        cell.props.markup = error_markup(text)
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
    msg = ''
    if state.csr.error:
        msg += 'E'
    if state.csr.current_overload:
        msg += 'I'
    if state.csr.base_voltage_error:
        msg += 'B'
    if state.csr.hardware_failure_error:
        msg += 'H'
    if state.csr.standby:
        msg += 'S'
    if state.csr.io_protection:
        msg += 'P'

    render_cell(cell, msg if msg else '--', 'error' if msg else 'ok', False)


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
        if self._state == 'warning':
            self.set_markup(warning_markup(self._text))
        elif self._state == 'warning':
            self.set_markup(error_markup(self._text))
        else:
            self.set_markup(f'{self._text}')


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

    def __init__(self, worker: Worker):
        super().__init__()

        self.worker = worker
        self.worker.connect(Worker.CELL_UPDATED, self._on_cell_updated)

        grid = Gtk.Grid()
        grid.set_column_spacing(4)
        grid.set_row_spacing(4)
        grid.set_margin_top(4)
        grid.set_margin_left(4)
        grid.set_margin_right(4)
        self.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA.from_color(Gdk.color_parse('white')))

        device_label = Gtk.Label()
        device_label.set_xalign(0)
        device_label.set_markup(f'Connected to <b>{self.worker.get_device_address()}</b>')
        grid.attach(device_label, 0, 0, 1, 1)

        self.error_label = ErrorLabel()
        grid.attach(self.error_label, 1, 0, 1, 1)

        self.tree_view, self.adapter = self._make_tree_view()
        scroll = Gtk.ScrolledWindow()
        scroll.add(self.tree_view)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        frame = Gtk.Frame()
        frame.add(scroll)
        frame.set_hexpand(True)
        grid.attach(frame, 0, 1, 2, 1)

        status_help = Gtk.Label(label=STATUS_HELP_TEXT)
        status_help.set_xalign(0)

        hbox = Gtk.Box()
        hbox.set_orientation(Gtk.Orientation.HORIZONTAL)
        hbox.pack_start(self._make_controller_dashboard(), True, True, 0)
        hbox.pack_start(status_help, False, False, 0)
        grid.attach(hbox, 0, 2, 2, 1)

        for cell in self.worker.iter_cells():
            self.adapter.append(cell)

        self.add(grid)

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

        adapter.append_text_column(tree_view, 'Errors\n*', cell_status_data_func)
        adapter.append_text_column(tree_view, 'Voltage\nrange, V', voltage_range_data_func)
        adapter.append_text_column(tree_view, 'Current limit\nrange, uA', current_limit_range_data_func)

        return tree_view, adapter

    def _make_controller_dashboard(self) -> Gtk.Grid:
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

        state_label = ParamLabel('state:')
        grid.attach(state_label, 0, 0, 1, 1)
        state_text = ParamLabel('')
        state_text.set_xalign(0)
        grid.attach(state_text, 1, 0, 6, 1)

        lv_text = attach_text_indicator('Low voltage:', 0, 1)
        bv_text = attach_text_indicator('Base voltage:', 0, 2)

        bv_on_desired = Gtk.Switch()
        bv_on_desired.connect('state-set', lambda _, b: self.worker.set_base_voltage_enabled(b))
        bv_on_actual = Gtk.Label()
        bv_on_label = attach_with_label('BV state:', 0, 3, bv_on_desired)
        grid.attach(bv_on_actual, 1, 4, 1, 1)

        t_proc_text = attach_text_indicator('T<sub>proc</sub>:', 3, 1)
        t_board_text = attach_text_indicator('T<sub>board</sub>:', 3, 2)
        t_power_text = attach_text_indicator('T<sub>power</sub>:', 3, 3)

        t_off = TempEditor(grid, 'T<sub>fan off</sub>:', 5, 1)
        t_off.connect('completed', lambda _, val: self.worker.set_fan_off_temp(val))
        t_on = TempEditor(grid, 'T<sub>fan on</sub>:', 5, 2)
        t_on.connect('completed', lambda _, val: self.worker.set_fan_on_temp(val))
        t_shutdown = TempEditor(grid, 'T<sub>shutdown</sub>:', 5, 3)
        t_shutdown.connect('completed', lambda _, val: self.worker.set_shutdown_temp(val))

        sensors = [
            (TemperatureSensor.microprocessor, 'uP'),
            (TemperatureSensor.board, 'board'),
            (TemperatureSensor.power_supply, 'power')
        ]
        indices = {s: i for i, (s, _) in enumerate(sensors)}

        t_sensor_desired = Gtk.ComboBoxText()
        t_sensor_desired.set_entry_text_column(0)
        t_sensor_desired.connect('changed', lambda cb: self.worker.set_temp_sensor(sensors[cb.get_active()][0]))
        t_sensor_actual = Gtk.ComboBoxText()
        t_sensor_actual.set_entry_text_column(0)
        t_sensor_actual.set_sensitive(False)
        t_sensor_label = attach_with_label('T sensor:', 5, 4, t_sensor_desired, t_sensor_actual)

        for ind, (s, sensor_text) in enumerate(sensors):
            t_sensor_desired.append_text(sensor_text)
            t_sensor_actual.append_text(sensor_text)

        def update_all(worker: Worker):
            state = worker.get_controller_state()

            lv_text.set_text(f'{state.low_voltage:.1f} V')
            bv_text.set_text(f'{state.base_voltage:.1f} V')

            bv_on_label.set_state('warning' if state.base_voltage_enabled.waiting else 'ok')
            bv_on_desired.set_active(state.base_voltage_enabled.desired)
            bv_on_actual.set_markup(
                ok_markup('enabled') if state.base_voltage_enabled.actual else error_markup('disabled'))

            t_proc_text.set_text(f'{state.processor_temp} \u00B0C')
            t_board_text.set_text(f'{state.board_temp} \u00B0C')
            t_power_text.set_text(f'{state.power_supply_temp} \u00B0C')

            t_off.update(state.fan_off_temp)
            t_on.update(state.fan_on_temp)
            t_shutdown.update(state.shutdown_temp)

            t_sensor_label.set_state('warning' if state.temp_sensor.waiting else 'ok')
            t_sensor_desired.set_active(indices[state.temp_sensor.desired])
            t_sensor_actual.set_active(indices[state.temp_sensor.actual])

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
                state_text.set_state('ok')

        update_all(self.worker)
        self.worker.connect(Worker.CONTROLLER_UPDATED, update_all)

        return grid

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
