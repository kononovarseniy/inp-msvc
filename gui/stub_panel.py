import logging
from typing import Optional

from gi.repository import Gtk, Gdk, GObject, GLib

from device.device import DeviceAddress
from gui.widgets.profile_label import create_profile_label
from gui.worker import Stage
from observable import Observable
from profile import Profile

LOGGER = logging.getLogger('stub-panel')


class StubPanel(Gtk.Grid):
    RECONNECT_CLICKED = 'reconnect-clicked'

    def __init__(self, address: DeviceAddress, stage: Stage, profile: Observable[Optional[Profile]]):
        super().__init__()

        self._address = address
        self._stage = stage

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

    def schedule_stage_change(self, new_stage: Stage):
        GLib.idle_add(StubPanel.stage.__set__, self, new_stage)

    @property
    def stage(self):
        return self._stage

    @stage.setter
    def stage(self, state: Stage):
        self._stage = state
        self._update()

    @property
    def address(self):
        return self._address

    def _update(self):
        self._connect_with_profile_button.hide()
        self._connect_without_profile_button.hide()
        if self._stage == Stage.CONNECTING:
            self._status_label.set_markup(f'Connecting to <b>{self._address}</b>')
        elif self._stage == Stage.WRITING_DEFAULTS:
            self._status_label.set_markup(f'Writing defaults to <b>{self._address}</b>')
        elif self._stage == Stage.READING_STATE:
            self._status_label.set_markup(f'Reading values from <b>{self._address}</b>')
        elif self._stage == Stage.CONNECTED:
            self._status_label.set_markup(f'Connected to <b>{self._address}</b>')
        elif self._stage == Stage.DISCONNECTED:
            self._status_label.set_markup(f'Connection to <b>{self.address}</b> failed')
            self._connect_with_profile_button.show()
            self._connect_without_profile_button.show()

    @GObject.Signal(name=RECONNECT_CLICKED)
    def _on_reconnect_clicked(self, use_profile: bool):
        pass
