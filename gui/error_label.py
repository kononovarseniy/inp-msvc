from gi.repository import Gtk, GLib


class ErrorLabel(Gtk.Label):
    def __init__(self):
        super().__init__()
        self.label_age = 0
        GLib.timeout_add(1000, self._update)

    def show_error(self, text: str):
        self.set_markup(f'<span foreground="red">{text}</span>')
        self.label_age = 0

    def _update(self):
        self.label_age += 1
        if self.label_age >= 5:
            self.set_markup('')

        return True
