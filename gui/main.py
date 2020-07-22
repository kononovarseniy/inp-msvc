import logging
from concurrent.futures import Future
from typing import List, Optional

import gi

from gui import files
from gui.worker import Worker

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
from gui.device_panel import DevicePanel

logging.basicConfig(level=logging.NOTSET)
LOGGER = logging.getLogger()


def main(args):
    try:
        win = MainWindow(args.devices)
        win.connect("destroy", Gtk.main_quit)
        win.show_all()
        Gtk.main()
    except KeyboardInterrupt:
        LOGGER.warning('Process interrupted')


class MainWindow(Gtk.Window):

    def __init__(self, device_list: Optional[str] = None):
        super().__init__()
        self.set_title('BINP muon system voltage controller')
        self.set_border_width(0)
        self.set_default_size(640, 480)

        devices = []
        try:
            if device_list is not None:
                devices = files.read_device_list(device_list)
        except FileNotFoundError:
            LOGGER.error(f'No such file: {device_list}')
        except ValueError:
            LOGGER.error(f'Failed to parse device list')

        notebook = Gtk.Notebook()

        self.panels: List[DevicePanel] = []
        panels: List[Optional[DevicePanel]] = [None] * len(devices)

        def worker_created(f: 'Future[Worker]'):
            worker = f.result()
            index = devices.index(worker.get_device_address())
            panels[index] = DevicePanel(worker)
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
