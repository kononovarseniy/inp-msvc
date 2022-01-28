from typing import TypeVar, Optional, Generic, Union, Any, Callable

from gi.repository import GLib, Gtk, GObject


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


T = TypeVar('T')


def get_row_being_edited(tree_view: Gtk.TreeView) -> Optional[Gtk.TreePath]:
    cur = tree_view.get_cursor()
    if cur.focus_column:
        col: Gtk.TreeViewColumn = cur.focus_column
        if any(c.props.editing for c in col.get_cells()):
            return cur.path
    return None


class GWrapper(GObject.GObject):
    """Wraps python object into GObject"""

    def __init__(self, value):
        GObject.GObject.__init__(self)
        self.value = value


class TreeModelAdapter(Generic[T]):
    def __init__(self):
        self.model = Gtk.ListStore(GWrapper)

    def get_row(self, item: Union[Gtk.TreeIter, Gtk.TreePath, str, int]) -> T:
        return self.model[item][0].value

    def __getitem__(self, item: Union[Gtk.TreeIter, Gtk.TreePath, str, int]):
        return self.get_row(item)

    def set_row(self, item: Union[Gtk.TreeIter, Gtk.TreePath, str, int], row: T):
        self.model[item] = [GWrapper(row)]

    def __setitem__(self, item: Union[Gtk.TreeIter, Gtk.TreePath, str, int], row: T):
        self.set_row(item, row)

    def __len__(self):
        return len(self.model)

    def row_changed(self, index: int):
        path = str(index)
        self.model.row_changed(path, self.model.get_iter(path))

    def append(self, row: Any):
        self.model.append([GWrapper(row)])

    def clear(self):
        self.model.clear()

    def _make_data_func(self, func: Callable[[Gtk.CellRenderer, T], None]):
        return lambda column, cell, model, it, _: func(cell, self.get_row(it))

    def _make_edited_signal_handler(self, parse: Callable[[str], Any], on_changed: Callable[[T, Any], bool]):
        def handler(_cell, path: str, new_text: str):
            try:
                val = parse(new_text)
            except ValueError:
                pass
            else:
                it = self.model.get_iter(path)
                if on_changed(self.get_row(it), val):
                    self.model.row_changed(path, it)

        return handler

    def _make_toggled_signal_handler(self, on_changed: Callable[[T, bool], bool]):
        def wrapper(cell, path: str):
            val = not cell.get_active()
            it = self.model.get_iter(path)
            if on_changed(self.get_row(it), val):
                self.model.row_changed(path, it)

        return wrapper

    def append_text_column(self, tree_view: Gtk.TreeView,
                           title: str,
                           data_func: Callable[[Gtk.CellRenderer, T], None],
                           parse_func: Optional[Callable[[str], Any]] = None,
                           on_changed: Optional[Callable[[T, Any], bool]] = None):
        renderer = Gtk.CellRendererText()

        editable = parse_func is not None and on_changed is not None
        if editable:
            assert parse_func is not None
            assert on_changed is not None
            renderer.props.editable = True
            renderer.connect('edited', self._make_edited_signal_handler(parse_func, on_changed))

        col = Gtk.TreeViewColumn(title, renderer)
        col.set_cell_data_func(renderer, self._make_data_func(data_func))
        tree_view.append_column(col)

    def append_toggle_column(self, tree_view: Gtk.TreeView,
                             title: str,
                             data_func: Callable[[Gtk.CellRenderer, T], None],
                             on_changed: Optional[Callable[[T, bool], bool]] = None):
        renderer = Gtk.CellRendererToggle()
        if on_changed:
            renderer.connect('toggled', self._make_toggled_signal_handler(on_changed))

        col = Gtk.TreeViewColumn(title, renderer)
        col.set_cell_data_func(renderer, self._make_data_func(data_func))
        tree_view.append_column(col)
