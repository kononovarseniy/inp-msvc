from gui.state import CellState
from gui.util import ErrorType


def is_in_range(v: float, r: (float, float)) -> bool:
    return r[0] <= v <= r[1]


def check_voltage_set(state: CellState) -> ErrorType:
    if not is_in_range(state.voltage_set.actual, state.voltage_range):
        return ErrorType.critical
    return ErrorType.ok


def check_measured_voltage(state: CellState) -> ErrorType:
    v_set = state.voltage_set.actual
    v_mes = state.voltage_measured

    if not is_in_range(v_mes, state.measured_voltage_range):
        return ErrorType.critical
    if state.enabled.actual and abs(v_set - v_mes) >= 1:
        return ErrorType.error
    if not state.enabled.actual and v_mes > 5:
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
