import logging
from concurrent.futures import Future
from functools import partial
from typing import List, Optional

from gi.repository import Gtk, Gio

from device.device import DeviceAddress
from gui import files
from gui.checks import ErrorType, DeviceErrorChecker
from gui.device_panel import DevicePanel
from gui.observable import Observable
from gui.stub_panel import StubPanel, State
from gui.util import glib_wait_future
from gui.widgets.status_label import create_status_label
from gui.worker import Worker, Profile

TITLE = 'Muon system voltage controller'

RESPONSE_RECONNECT = 1
RESPONSE_RECONNECT_WITH_PROFILE = 2
RESPONSE_RECONNECT_WITHOUT_PROFILE = 3
RESPONSE_DISCONNECT = 4

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


def show_simple_reconnect_dialog(parent, address: DeviceAddress, msg: str) -> int:
    dlg = Gtk.MessageDialog(
        parent=parent,
        type=Gtk.MessageType.ERROR,
        buttons=(
            'Reconnect', RESPONSE_RECONNECT,
            'Disconnect', RESPONSE_DISCONNECT
        ),
        message_format=f'{address}\nConnection failure. Reconnect?'
    )
    dlg.set_title(TITLE)
    dlg.format_secondary_text(f'{msg}\nDo you want to try again?')
    response = dlg.run()
    dlg.destroy()
    return response


def show_reconnect_dialog(parent, address: DeviceAddress, msg: str) -> int:
    dlg = Gtk.MessageDialog(
        parent=parent,
        type=Gtk.MessageType.ERROR,
        buttons=(
            'Reconnect, use profile', RESPONSE_RECONNECT_WITH_PROFILE,
            'Reconnect, read device state', RESPONSE_RECONNECT_WITHOUT_PROFILE,
            'Disconnect', RESPONSE_DISCONNECT
        ),
        message_format=f'{address}\nConnection failure. Reconnect?'
    )
    dlg.set_title(TITLE)
    dlg.format_secondary_text(f'{msg}\n'
                              f'You have several options:\n'
                              f'\t1) Reconnect and set parameters from current device profile\n'
                              f'\t2) Reconnect and read device state without altering it\n'
                              f'\t3) Disconnect')
    response = dlg.run()
    dlg.destroy()
    return response


def show_profile_chooser_dialog(parent, title: str) -> Optional[str]:
    dlg = Gtk.FileChooserDialog(
        title=title,
        parent=parent,
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

    dlg.run()
    file = dlg.get_filename()
    dlg.destroy()
    return file


class WorkerWrapper:
    def __init__(self, address: DeviceAddress):
        self._address = address
        self._worker: Optional[Worker] = None
        self._error = Observable(ErrorType.ok)
        # noinspection PyCallingNonCallable
        self._profile = Observable[Optional[Profile]](None)
        self._profile.add_observer(lambda _: self._load_profile())

    def _load_profile(self):
        try:
            if self._worker is not None and self.profile.value is not None:
                self._worker.load_device_profile(self.profile.value[self.address])
        except IndexError:
            LOGGER.error(f'Unable to load profile: the voltage cell with specified index does not exist')
        except ValueError as e:
            LOGGER.error(f'Unable to load profile: {self._worker.get_device_address()} {e}')

    @property
    def address(self):
        return self._address

    @property
    def worker(self) -> Optional[Worker]:
        return self._worker

    @worker.setter
    def worker(self, value: Optional[Worker]):
        self._worker = value
        self._load_profile()

    @property
    def error(self) -> Observable[ErrorType]:
        return self._error

    @property
    def profile(self) -> Observable[Profile]:
        return self._profile


class MainWindow(Gtk.ApplicationWindow):

    def __init__(self, devices: List[DeviceAddress], profile: Optional[Profile]):
        super().__init__()
        self.set_title(TITLE)
        self.set_border_width(0)
        self.set_default_size(700, 480)

        self.wrappers: List[WorkerWrapper] = []

        self.notebook = Gtk.Notebook()
        self.notebook.set_hexpand(True)
        self.notebook.set_vexpand(True)

        for i, dev in enumerate(devices):
            wrapper = WorkerWrapper(dev)
            wrapper.profile.value = profile
            self.wrappers.append(wrapper)

            tab_body = Gtk.Box()
            tab_body.pack_start(StubPanel(dev, State.CONNECTING, wrapper.profile), True, True, 0)
            self.notebook.append_page(tab_body, create_status_label(dev.name, wrapper.error))

            glib_wait_future(Worker.create(dev), self.on_worker_created, i)

        # a grid to attach the widgets
        grid = Gtk.Grid()
        grid.attach(_create_menubar(), 0, 0, 1, 1)
        grid.attach(self.notebook, 0, 1, 1, 1)

        # attach the grid to the window
        self.add(grid)

        self.add_action(_new_action('file.load_all', self.on_load_all))
        self.add_action(_new_action('file.load_one', self.on_load_one))

    def set_nth_page(self, index, panel):
        tab = self.notebook.get_nth_page(index)
        for c in tab.get_children():
            c.destroy()
        tab.pack_start(panel, True, True, 0)
        self.notebook.show_all()

    def show_stub_page(self, index: int):
        wrapper = self.wrappers[index]
        panel = StubPanel(wrapper.address, State.DISCONNECTED, wrapper.profile)
        panel.connect(StubPanel.RECONNECT_CLICKED, lambda _, use_profile: self.reconnect_device(use_profile, index))
        self.set_nth_page(index, panel)

    def reconnect_device(self, use_profile: bool, index: int):
        wrapper = self.wrappers[index]
        wrapper.worker = None
        if use_profile:
            LOGGER.info(f'Reconnecting to {wrapper.address} using current profile')
            glib_wait_future(Worker.create(wrapper.address), self.on_worker_created, index)
        else:
            LOGGER.info(f'Reconnecting to {wrapper.address} without profile')
            wrapper.profile.value = None
            glib_wait_future(Worker.create(wrapper.address), self.on_worker_created, index)

    def disconnect_device(self, index: int):
        wrapper = self.wrappers[index]
        LOGGER.info(f'Disconnecting from {wrapper.address}')
        wrapper.worker = None
        self.show_stub_page(index)

    def on_worker_created(self, f: 'Future[Worker]', index: int):
        wrapper = self.wrappers[index]
        try:
            worker = f.result()
        except ConnectionError as e:
            LOGGER.error(e)
            response = show_simple_reconnect_dialog(self, wrapper.address, str(e))

            if response == RESPONSE_RECONNECT:
                self.reconnect_device(True, index)
            else:
                self.disconnect_device(index)
            return

        LOGGER.info(f'Connected to {worker.get_device_address()}')
        wrapper.worker = worker
        worker.connect(Worker.CONNECTION_ERROR, partial(self.on_connection_error, index=index))

        DeviceErrorChecker(worker, output=wrapper.error)  # Connects itself to worker signals

        self.set_nth_page(index, DevicePanel(worker, wrapper.profile))

    def on_connection_error(self, _: Worker, msg: str, *, index: int):
        self.wrappers[index].error.value = ErrorType.critical
        response = show_reconnect_dialog(self, self.wrappers[index].address, msg)

        if response == RESPONSE_RECONNECT_WITH_PROFILE:
            self.reconnect_device(True, index)
        elif response == RESPONSE_RECONNECT_WITHOUT_PROFILE:
            self.reconnect_device(False, index)
        else:
            self.disconnect_device(index)

    def read_profile(self, title: str):
        profile = show_profile_chooser_dialog(self, title)
        if profile is None:
            LOGGER.info('Profile is not loaded')
            return None

        try:
            return files.read_profile(profile)
        except IOError as e:
            LOGGER.error(f'Cannot read profile: {e}')
        except files.FormatError as e:
            LOGGER.error(f'Invalid profile: {e.message}')

    def on_load_all(self, _action, _value):
        profile = self.read_profile("Chose profile for all devices...")
        if profile is None:
            return

        for w in self.wrappers:
            w.profile.value = profile

    def on_load_one(self, _action, _value):
        profile = self.read_profile("Chose profile for selected device...")
        if profile is None:
            return

        page = self.notebook.get_current_page()
        self.wrappers[page].profile.value = profile
