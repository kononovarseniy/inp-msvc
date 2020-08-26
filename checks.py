from enum import IntEnum

from settings import check_settings
from observable import Observable
from state import CellState, DeviceParameter, ControllerState
from gui.worker import Worker


class ErrorType(IntEnum):
    ok = 0  # Must be less than other constants
    good = 1
    warning = 2
    error = 3
    critical = 4


def is_in_range(v: float, r: (float, float)) -> bool:
    return r[0] <= v <= r[1]


def check_actual_voltage_set(state: CellState) -> ErrorType:
    if not is_in_range(state.voltage_set.actual, state.voltage_range):
        return ErrorType.critical
    return ErrorType.ok


def check_measured_voltage(state: CellState) -> ErrorType:
    v_set = state.voltage_set.actual
    v_mes = state.voltage_measured

    if not is_in_range(v_mes, state.measured_voltage_range):
        return ErrorType.critical
    if state.enabled.actual and abs(v_set - v_mes) >= check_settings.max_voltage_difference:
        return ErrorType.error
    if not state.enabled.actual and v_mes > check_settings.max_voltage_when_off:
        return ErrorType.error
    return ErrorType.ok


def check_measured_current(state: CellState) -> ErrorType:
    i_lim = state.current_limit.actual
    i_mes = state.current_measured

    if not is_in_range(i_mes, state.measured_current_range):
        return ErrorType.critical

    if i_mes > i_lim:
        return ErrorType.error

    return ErrorType.ok


def check_cell_status(state: CellState) -> ErrorType:
    if state.csr.current_overload or \
            state.csr.base_voltage_error or \
            state.csr.hardware_failure_error or \
            state.csr.standby or \
            state.csr.io_protection:
        return ErrorType.error
    return ErrorType.ok


def check_parameter(state: DeviceParameter) -> ErrorType:
    if state.waiting:
        return ErrorType.warning
    else:
        return ErrorType.ok


def good_if_output_enabled(state: CellState) -> ErrorType:
    return ErrorType.good if state.enabled.actual else ErrorType.ok


def check_cell(state: CellState) -> ErrorType:
    return max(
        check_actual_voltage_set(state),
        check_measured_voltage(state),
        check_measured_current(state),
        check_cell_status(state),
        check_parameter(state.voltage_set),
        check_parameter(state.current_limit),
        check_parameter(state.enabled),
        check_parameter(state.ramp_up_speed),
        check_parameter(state.ramp_down_speed),
        good_if_output_enabled(state)
    )


def check_controller(state: ControllerState) -> ErrorType:
    return max(
        check_parameter(state.fan_off_temp),
        check_parameter(state.fan_on_temp),
        check_parameter(state.shutdown_temp)
    )


class DeviceErrorChecker:
    def __init__(self, worker: Worker, output: Observable[ErrorType]):
        self._output = output
        worker.connect(Worker.CELL_UPDATED, lambda w, _: self._on_updated(w))
        worker.connect(Worker.CONTROLLER_UPDATED, lambda w: self._on_updated(w))

    def _on_updated(self, worker: Worker):
        res = max(map(check_cell, worker.iter_cells()))
        res = max(res, check_controller(worker.get_controller_state()))
        self._output.value = res
