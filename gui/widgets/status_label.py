from gi.repository import Gtk

from checks import ErrorType
from gui.markup import make_markup
from observable import Observable


def create_status_label(text: str, error_observable: Observable[ErrorType]):
    def on_destroy(_):
        error_observable.remove_observer(on_update)

    def on_update(error):
        label.set_markup(make_markup(error.value, text))

    label = Gtk.Label()
    label.connect('destroy', on_destroy)
    on_update(error_observable)
    error_observable.add_observer(on_update)

    return label
