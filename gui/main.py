import logging

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
from device.worker import DeviceAddress
from gui.device_panel import DevicePanel

logging.basicConfig(level=logging.NOTSET)
LOGGER = logging.getLogger()


class MainWindow(Gtk.Window):

    def __init__(self):
        super().__init__()
        self.set_title('BINP muon system voltage controller')
        self.set_border_width(8)
        self.set_default_size(640, 480)

        self.device_panel = DevicePanel()
        self.device_panel.connect('started', self.on_panel_started)
        self.device_panel.start(DeviceAddress('dev1', ('127.0.0.1', 8080)))

        # a grid to attach the widgets
        grid = Gtk.Grid()
        grid.attach(self.device_panel, 0, 0, 1, 1)

        # attach the grid to the window
        self.add(grid)

    def on_panel_started(self, panel: DevicePanel):
        panel.start_update()
        GLib.timeout_add(2000, self.on_timer)

    def on_timer(self):
        if not self.device_panel.is_connected():
            return False
        self.device_panel.start_update()
        return True


if __name__ == '__main__':
    try:
        win = MainWindow()
        win.connect("destroy", Gtk.main_quit)
        win.show_all()
        Gtk.main()
    except KeyboardInterrupt:
        LOGGER.warning('Process interrupted')
