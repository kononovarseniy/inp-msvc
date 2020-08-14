import logging
from concurrent.futures import Future
from typing import List, Optional

from gi.repository import Gtk, GLib, Gio

import gui.worker
from device.device import DeviceAddress
from gui import files
from gui.device_panel import DevicePanel
from gui.worker import Worker

LOGGER = logging.getLogger('MainWindow')


def _new_action(name, on_activate):
    action = Gio.SimpleAction.new(name)
    action.connect('activate', on_activate)
    return action


def _create_menubar():
    file_menu = Gio.Menu()
    file_menu.append_item(Gio.MenuItem.new('Load profile for all devices...', 'win.file.load_all'))
    file_menu.append_item(Gio.MenuItem.new('Load profile for selected device...', 'win.file.load_one'))

    help_menu = Gio.Menu()
    help_menu.append_item(Gio.MenuItem.new('About', 'win.help.about'))

    menu_model = Gio.Menu()
    menu_model.append_submenu('File', file_menu)
    menu_model.append_submenu('Help', help_menu)

    return Gtk.MenuBar.new_from_model(menu_model)


class WorkerWrapper:
    def __init__(self):
        self._worker: Optional[Worker] = None
        self._profile: Optional[gui.worker.DeviceProfile] = None

    def _load_profile(self):
        try:
            if self._worker is not None and self._profile is not None:
                self._worker.load_device_profile(self._profile)
        except IndexError:
            LOGGER.error(f'Unable to load profile: the voltage cell with specified index does not exist')
        except ValueError as e:
            LOGGER.error(f'Unable to load profile: {self._worker.get_device_address()} {e}')

    @property
    def worker(self) -> Optional[Worker]:
        return self._worker

    @worker.setter
    def worker(self, value: Optional[Worker]):
        self._worker = value
        self._load_profile()

    @property
    def profile(self) -> Optional[gui.worker.DeviceProfile]:
        return self._profile

    @profile.setter
    def profile(self, value: Optional[gui.worker.DeviceProfile]):
        self._profile = value
        self._load_profile()

    def set_profile(self, value: gui.worker.Profile):
        self.profile = value[self._worker.get_device_address().name]


class MainWindow(Gtk.ApplicationWindow):

    def __init__(self, devices: List[DeviceAddress], profile: Optional[gui.worker.Profile]):
        super().__init__()
        self.set_title('Muon system voltage controller')
        self.set_border_width(0)
        self.set_default_size(700, 480)

        self.wrappers: List[WorkerWrapper] = []

        self.notebook = Gtk.Notebook()
        self.notebook.set_hexpand(True)
        self.notebook.set_vexpand(True)

        def make_done_callback(index: int):
            return lambda f: GLib.idle_add(self.on_worker_created, f, index)

        for i, dev in enumerate(devices):
            label = Gtk.Label()
            label.set_markup(f'Connecting to <b>{dev}</b>')

            container = Gtk.Box()
            container.pack_start(label, True, True, 0)

            self.notebook.append_page(container, Gtk.Label(label=dev.name))

            wrapper = WorkerWrapper()
            wrapper.profile = profile[dev.name]
            self.wrappers.append(wrapper)

            Worker.create(dev).add_done_callback(make_done_callback(i))

        self.notebook.show_all()

        # a grid to attach the widgets
        grid = Gtk.Grid()
        grid.attach(_create_menubar(), 0, 0, 1, 1)
        grid.attach(self.notebook, 0, 1, 1, 1)

        # attach the grid to the window
        self.add(grid)

        self.add_action(_new_action('file.load_all', self.on_load_all))
        self.add_action(_new_action('file.load_one', self.on_load_one))

    def on_worker_created(self, f: 'Future[Worker]', index: int):
        worker = self.wrappers[index].worker = f.result()

        tab = self.notebook.get_nth_page(index)
        for c in tab.get_children():
            tab.remove(c)
        tab.pack_start(DevicePanel(worker), True, True, 0)

        self.notebook.show_all()

    def choose_profile(self, title: str) -> Optional[str]:
        dlg = Gtk.FileChooserDialog(
            title=title,
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
            buttons=(
                Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                Gtk.STOCK_OPEN, Gtk.ResponseType.OK
            ))

        file_filter = Gtk.FileFilter()
        file_filter.set_name("CSV files")
        file_filter.add_pattern("*.csv")
        dlg.add_filter(file_filter)

        file_filter = Gtk.FileFilter()
        file_filter.set_name("All files")
        file_filter.add_pattern("*")
        dlg.add_filter(file_filter)

        res = dlg.run()
        if res == Gtk.ResponseType.OK:
            profile = dlg.get_filename()
            LOGGER.info(f'Profile chosen: {profile}')
        else:
            profile = None
            LOGGER.info('Profile not chosen')
        dlg.destroy()
        return profile

    def read_profile(self, title: str):
        profile = self.choose_profile(title)
        if profile is None:
            LOGGER.info('Profile is not loaded')
            return None

        try:
            return files.read_profile(profile)
        except IOError as e:
            LOGGER.error(f'Cannot read profile: {e}')
        except files.FormatError as e:
            LOGGER.error(f'Invalid profile: {e.message}')

    def on_load_all(self, action, value):
        profile = self.read_profile("Chose profile for all devices...")
        if profile is None:
            return

        for w in self.wrappers:
            w.set_profile(profile)

    def on_load_one(self, action, value):
        profile = self.read_profile("Chose profile for selected device...")
        if profile is None:
            return

        page = self.notebook.get_current_page()
        self.wrappers[page].set_profile(profile)
