import logging

from gi.repository import Gtk

from gui import files
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

    profile = None
    try:
        if args.profile is not None:
            profile = files.read_profile(args.profile)
    except IOError as e:
        LOGGER.error(f'Failed to read profile: {e}')
    except files.FormatError as e:
        LOGGER.error(f'Failed to parse profile {e}')

    if profile is not None:
        names1 = set(addr.name for addr in devices)
        names2 = set(profile.keys())

        diff = names2 - names1
        if len(diff) > 0:
            LOGGER.error(f'Voltage profile uses some unknown device names: {diff}')

        diff = names1 - names2
        if len(diff) > 0:
            LOGGER.warning(f'The profile does not contain parameters for some devices: {diff}')

    win = MainWindow(devices, profile)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
