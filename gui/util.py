from gi.repository import GLib


def glib_wait_future(future, func, *args):
    future.add_done_callback(lambda _: GLib.idle_add(func, future, *args))
