import logging
from concurrent.futures import Future
from typing import List, Optional

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
        self.set_title('BINP muon system voltage controller')
        self.set_border_width(0)
        self.set_default_size(640, 480)

        notebook = Gtk.Notebook()

        self.panels: List[DevicePanel] = []
        panels: List[Optional[DevicePanel]] = [None] * len(devices)

        def worker_created(f: 'Future[Worker]'):
            worker = f.result()
            address = worker.get_device_address()
            index = devices.index(address)
            panels[index] = DevicePanel(worker)
            if profile is not None:
                try:
                    worker.set_values(profile[address.name])
                except ValueError as e:
                    LOGGER.error(f'Unable to load values from profile: {address} {e}')
            if all(p is not None for p in panels):
                for p in panels:
                    self.panels.append(p)
                    notebook.append_page(p, Gtk.Label(label=p.worker.get_device_address().name))
                notebook.show_all()

        for i, dev in enumerate(devices):
            Worker.create(dev).add_done_callback(lambda f: GLib.idle_add(worker_created, f))

        # a grid to attach the widgets
        grid = Gtk.Grid()
        grid.attach(notebook, 0, 0, 1, 1)

        # attach the grid to the window
        self.add(grid)
