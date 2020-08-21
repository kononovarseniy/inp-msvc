import logging
from enum import Enum
from typing import Optional

from gi.repository import Gtk, Gdk, GObject

from device.device import DeviceAddress
from gui.observable import Observable
from gui.widgets.profile_label import create_profile_label
from gui.worker import Profile

LOGGER = logging.getLogger('stub-panel')


class State(Enum):
    CONNECTING = 1
    DISCONNECTED = 2


class StubPanel(Gtk.Grid):
    RECONNECT_CLICKED = 'reconnect-clicked'

    def __init__(self, address: DeviceAddress, state: State, profile: Observable[Optional[Profile]]):
        super().__init__()

        self._address = address
        self._state = state

        self.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA.from_color(Gdk.color_parse('white')))

        self._status_label = Gtk.Label()
        profile_label = create_profile_label(profile)
        profile_label.set_xalign(0)

        self._connect_with_profile_button = Gtk.Button('Connect, use profile')
        self._connect_with_profile_button.set_no_show_all(True)
        self._connect_with_profile_button.connect('clicked', lambda _: self.emit(StubPanel.RECONNECT_CLICKED, True))

        self._connect_without_profile_button = Gtk.Button('Connect, read device state')
        self._connect_without_profile_button.set_no_show_all(True)
        self._connect_without_profile_button.connect('clicked', lambda _: self.emit(StubPanel.RECONNECT_CLICKED, False))

        grid = Gtk.Grid()
        grid.set_column_spacing(4)
        grid.set_row_spacing(4)
        grid.set_valign(Gtk.Align.CENTER)
        grid.set_halign(Gtk.Align.CENTER)
        grid.set_hexpand(True)
        grid.set_vexpand(True)
        grid.attach(self._status_label, 0, 0, 2, 1)
        grid.attach(profile_label, 0, 1, 2, 1)
        grid.attach(self._connect_with_profile_button, 0, 2, 1, 1)
        grid.attach(self._connect_without_profile_button, 1, 2, 1, 1)

        self.attach(grid, 0, 0, 1, 1)

        self._update()

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, state: State):
        self._state = state
        self._update()

    @property
    def address(self):
        return self._address

    def _update(self):
        if self._state == State.CONNECTING:
            self._status_label.set_markup(f'Connecting to <b>{self._address}</b>')
            self._connect_with_profile_button.hide()
            self._connect_without_profile_button.hide()
        elif self._state == State.DISCONNECTED:
            self._status_label.set_markup(f'Connection to <b>{self.address}</b> failed')
            self._connect_with_profile_button.show()
            self._connect_without_profile_button.show()

    @GObject.Signal(name=RECONNECT_CLICKED)
    def _on_reconnect_clicked(self, use_profile: bool):
        pass
