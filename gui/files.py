import csv
import logging
from collections import defaultdict

from device.device import DeviceAddress
from gui.worker import DeviceProfile, Profile
from gui.state import CellSettings


class FormatError(Exception):
    def __init__(self, msg: str):
        self.message = msg


LOGGER = logging.getLogger('files')


def read_device_list(file: str):
    with open(file, 'r') as f:
        reader = csv.reader(f, skipinitialspace=True)
        header = next(reader)
        expected = ['name', 'address', 'port']
        if header != expected:
            LOGGER.warning(f'Wrong csv file header. Expected: {expected}, Actual: {header}')
            return None
        res = []
        for row in reader:
            try:
                name, address, port = row
                res.append(DeviceAddress(name, (address, int(port))))
            except ValueError:
                LOGGER.error(f'Wrong row format at line {reader.line_num}')
                raise
        return res


def read_profile(file: str) -> Profile:
    with open(file, 'r') as f:
        reader = csv.reader(f, skipinitialspace=True)
        header = next(reader)
        expected = ['device', 'cell_index', 'auto_enable', 'voltage', 'current_limit', 'ramp_up', 'ramp_down']
        if header != expected:
            raise FormatError(f'Wrong csv file header. Expected: {expected}, Actual: {header}')
        res = Profile(file)
        for row in reader:
            try:
                device, cell_index, auto_enable, voltage, cur_lim, ramp_up, ramp_down = row
                settings = CellSettings(False, float(voltage), float(cur_lim),
                                        int(ramp_up), int(ramp_down), auto_enable.lower() == 'true')
                cell_index = int(cell_index)
                res[device].cell_settings[cell_index] = settings
            except ValueError as e:
                raise FormatError(f'Wrong row format at line {reader.line_num}: {e}')
        return res
