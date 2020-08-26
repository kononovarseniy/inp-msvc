import logging

from gi.repository import Gtk

import files
from gui.main_window import MainWindow

LOGGER = logging.getLogger('gui')


def main(args):
    devices = []
    try:
        if args.devices is not None:
            devices = files.read_device_list(args.devices)
    except FileNotFoundError:
        LOGGER.error(f'No such file: {args.devices}')
    except ValueError:
        LOGGER.error(f'Failed to parse device list')

    win = MainWindow(devices)
    win.connect('destroy', Gtk.main_quit)
    if args.profile is not None:
        win.set_profile(args.profile, None)
    win.show_all()
    Gtk.main()
