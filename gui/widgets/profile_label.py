from typing import Optional

from gi.repository import Gtk, GLib

from observable import Observable
from profile import Profile


def create_profile_label(observable_profile: Observable[Optional[Profile]]):
    def on_destroy(_):
        observable_profile.remove_observer(on_update)

    def on_update(profile):
        if profile.value:
            label.set_markup(f'Profile: <b>{GLib.markup_escape_text(profile.value.filename)}</b>')
        else:
            label.set_markup(f'Profile: <b>not set</b>')

    label = Gtk.Label()
    label.connect('destroy', on_destroy)
    on_update(observable_profile)
    observable_profile.add_observer(on_update)

    return label
