import csv
import logging

from device.device import DeviceAddress

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
