from dataclasses import dataclass
from typing import Dict, Optional

from device.registers import ControllerRegister, CellRegister


@dataclass
class DefaultValues:
    controller: Dict[ControllerRegister, int]
    cell: Dict[CellRegister, int]


defaults: Optional[DefaultValues] = None
