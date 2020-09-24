import argparse
import logging
import sys

import gi

gi.require_version("Gtk", "3.0")

# Read configuration, ignore unused import
# noinspection PyUnresolvedReferences
import config
# NOTE: before this line only standard library modules can be imported


from settings import program_settings
from gui.main import main as gui_main
from data_logger import DataLogger

LOGGER = logging.getLogger()


def excepthook(exc_type, value, traceback):
    LOGGER.critical("Uncaught exception", exc_info=(exc_type, value, traceback))


if __name__ == '__main__':
    try:
        sys.excepthook = excepthook

        parser = argparse.ArgumentParser(description='Muon system voltage controller.')
        parser.add_argument('devices', metavar='DEVICES', help='Path to a CSV file containing device addresses')
        parser.add_argument('--profile', metavar='PATH',
                            help='Path to a CSV file containing parameters of voltage cells')

        args = parser.parse_args()
        data_logger = DataLogger(program_settings.data_log_file)

        gui_main(args, data_logger)
    except KeyboardInterrupt:
        LOGGER.warning('Process interrupted')
