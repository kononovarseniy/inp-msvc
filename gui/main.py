import logging
from typing import List, Optional

import gi

from gui import files

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

        self.panel_init_countdown = len(devices)
        self.panels: List[DevicePanel] = []
        for dev in devices:
            panel = DevicePanel()
            self.panels.append(panel)
            panel.connect('started', self.on_panel_started)
            panel.start(dev)
            notebook.append_page(panel, Gtk.Label(label=dev.name))

        # a grid to attach the widgets
        grid = Gtk.Grid()
        grid.attach(notebook, 0, 0, 1, 1)

        # attach the grid to the window
        self.add(grid)

    def on_panel_started(self, panel: DevicePanel):
        panel.start_update()
        self.panel_init_countdown -= 1
        if self.panel_init_countdown == 0:
            GLib.timeout_add(2000, self.on_timer)

    def on_timer(self):
        for panel in self.panels:
            panel.start_update()

        return True
