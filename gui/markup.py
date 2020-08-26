from typing import Any

from gi.repository import Gtk

from checks import ErrorType


def warning_markup(text: Any) -> str:
    return f'<span background="yellow" foreground="black">{text}</span>'


def error_markup(text: Any) -> str:
    return f'<span background="red" foreground="white" weight="bold">{text}</span>'


def critical_markup(text: Any) -> str:
    return f'<span background="purple" foreground="white" weight="bold">{text}</span>'


def good_markup(text: Any) -> str:
    return f'<span background="green" foreground="white" weight="bold">{text}</span>'


def make_markup(error_type: ErrorType, text: Any) -> str:
    if error_type == ErrorType.good:
        return good_markup(text)

    if error_type == ErrorType.ok:
        return str(text)

    if error_type == ErrorType.warning:
        return warning_markup(text)

    if error_type == ErrorType.error:
        return error_markup(text)

    if error_type == ErrorType.critical:
        return critical_markup(text)


def render_cell(cell: Gtk.CellRenderer, text: Any, error_type: ErrorType, editable: bool):
    cell.props.markup = make_markup(error_type, text)

    if error_type == ErrorType.good:
        cell.props.cell_background = 'green'

    if error_type == ErrorType.ok:
        cell.props.cell_background = 'white' if editable else 'light gray'

    if error_type == ErrorType.warning:
        cell.props.cell_background = 'yellow'

    if error_type == ErrorType.error:
        cell.props.cell_background = 'red'

    if error_type == ErrorType.critical:
        cell.props.cell_background = 'purple'
