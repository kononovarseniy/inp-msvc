import logging
from concurrent.futures import Future
from typing import List

from gi.repository import Gtk, GLib

from device.device import DeviceAddress
from gui import files
from gui.device_panel import DevicePanel
from gui.worker import Worker

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
    except FileNotFoundError:
        LOGGER.error(f'No such file: {args.profile}')
    except ValueError:
        LOGGER.error(f'Failed to parse profile file')

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


class MainWindow(Gtk.Window):

    def __init__(self, devices: List[DeviceAddress], profile: files.Profile):
        super().__init__()
        self.set_title('Muon system voltage controller')
        self.set_border_width(0)
        self.set_default_size(700, 480)

        notebook = Gtk.Notebook()
        notebook.set_hexpand(True)
        notebook.set_vexpand(True)
        dev_to_tab = dict()

        def worker_created(f: 'Future[Worker]'):
            worker = f.result()
            address = worker.get_device_address()
            panel = DevicePanel(worker)
            tab = dev_to_tab[address]
            for c in tab.get_children():
                tab.remove(c)
            tab.pack_start(panel, True, True, 0)
            notebook.show_all()

            if profile is not None:
                try:
                    worker.apply_settings_to_cells(profile[address.name])
                except ValueError as e:
                    LOGGER.error(f'Unable to load values from profile: {address} {e}')

        for i, dev in enumerate(devices):
            container = Gtk.Box()
            label = Gtk.Label()
            label.set_markup(f'Connecting to <b>{dev}</b>')
            container.pack_start(label, True, True, 0)
            dev_to_tab[dev] = container
            notebook.append_page(container, Gtk.Label(label=dev.name))

            Worker.create(dev).add_done_callback(lambda f: GLib.idle_add(worker_created, f))

        notebook.show_all()

        # a grid to attach the widgets
        grid = Gtk.Grid()
        grid.attach(notebook, 0, 0, 1, 1)

        # attach the grid to the window
        self.add(grid)
