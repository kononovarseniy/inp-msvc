from gi.repository import Gtk, GLib

from gui.observable import Observable


def create_error_label(error_text: Observable[str]):
    alive = True
    label_age = 0

    def on_destroy(_):
        nonlocal alive
        error_text.remove_observer(on_update)
        alive = False

    def on_update(text):
        nonlocal label_age
        label.set_markup(f'<span foreground="red">{text.value}</span>')
        label_age = 0

    def on_timer():
        nonlocal label_age
        if not alive:
            return False
        label_age += 1
        if label_age >= 5:
            label.set_markup('')

        return True

    label = Gtk.Label()
    label.connect('destroy', on_destroy)
    on_update(error_text)
    error_text.add_observer(on_update)
    GLib.timeout_add(1000, on_timer)

    return label
