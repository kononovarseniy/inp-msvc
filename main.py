import argparse
import logging
import sys

import gi

gi.require_version("Gtk", "3.0")

# Read configuration, ignore unused import
# noinspection PyUnresolvedReferences
import config

from gui.main import main

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

        main(args)
    except KeyboardInterrupt:
        LOGGER.warning('Process interrupted')
