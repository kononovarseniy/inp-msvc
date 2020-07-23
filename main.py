import argparse
import logging

import gi

gi.require_version("Gtk", "3.0")

from gui.main import main

logging.basicConfig(level=logging.NOTSET)
LOGGER = logging.getLogger()

if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description='Muon system voltage controller.')
        parser.add_argument('devices', metavar='DEVICES', help='Path to a CSV file containing device addresses')
        parser.add_argument('--profile', metavar='PATH',
                            help='Path to a CSV file containing parameters of voltage cells')

        args = parser.parse_args()

        main(args)
    except KeyboardInterrupt:
        LOGGER.warning('Process interrupted')
