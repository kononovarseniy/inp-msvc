from collections import defaultdict
from typing import Dict, Union, Iterable

from device.device import DeviceAddress
from state import CellSettings


class DeviceProfile:
    def __init__(self):
        self.cell_settings: Dict[int, CellSettings] = dict()


class Profile:
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
