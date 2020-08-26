from gi.repository import GLib, Gtk


def glib_wait_future(future, func, *args):
    future.add_done_callback(lambda _: GLib.idle_add(func, future, *args))


class NumberEntry(Gtk.Entry, Gtk.Editable):
    def __init__(self):
        super().__init__()

    def do_insert_text(self, new_text, length, position):
        if all(c.isdigit() for c in new_text):
            self.get_buffer().insert_text(position, new_text, length)
            return position + len(new_text)
        else:
            return position
