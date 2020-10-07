"""Contains classes to represent parameters read from a file and written to the device at startup"""

from collections import defaultdict
from typing import Dict, Union, Iterable

from device.device import DeviceAddress
from state import CellSettings


class DeviceProfile:
    """Settings for all cells of one device"""

    def __init__(self):
        self.cell_settings: Dict[int, CellSettings] = dict()


class Profile:
    """
    Dictionary of (device-name, device-profile) pairs.
    If the specified device-name is not found, the device-profile is empty.
    """

    def __init__(self, filename: str):
        super().__init__()
        self._dict = defaultdict(DeviceProfile)
        self.filename = filename

    def __getitem__(self, device: Union[str, DeviceAddress]):
        if isinstance(device, DeviceAddress):
            device = device.name
        return self._dict[device]

    def device_names(self) -> Iterable[str]:
        return self._dict.keys()
