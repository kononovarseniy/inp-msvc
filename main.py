import argparse

from gui.main import main

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Muon system voltage controller.')
    parser.add_argument('--devices', metavar='PATH', help='Path to a CSV file containing device addresses')

    args = parser.parse_args()
    main(args)
