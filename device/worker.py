import logging
from concurrent.futures import Future
from concurrent.futures.thread import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Tuple, List, Optional

from device.device import Device, Cell

CHANNEL_COUNT = 16

SOCKET_TIMEOUT = 10

logger = logging.getLogger("Worker")
logger.setLevel(logging.INFO)


@dataclass
class DeviceAddress:
    name: str
    address: Tuple[str, int]

    def __str__(self) -> str:
        return f"{self.name}@{self.address[0]}:{self.address[1]}"


@dataclass
class CellState:
    index: int
    """Cell index, numbering from one"""
    enabled: bool
    """Indicates whether the output voltage is on"""
    voltage_set: float
    """Desired output voltage in volts"""
    voltage_measured: float
    """Measured output voltage in volts"""
    current_measured: float
    """Measured current in mcA"""
    current_limit: float
    """Current limit in mcA"""
    ramp_up: int
    """Ramp up value in V/s"""
    ramp_down: int
    """Ramp down value in V/s"""
    current_limit_range: Tuple[float, float]
    """The range of valid values of current_limit"""
    output_voltage_range: Tuple[float, float]
    """The range of valid values of voltage_set"""


@dataclass
class DeviceState:
    cells: List[CellState]


def _read_cell_status(cell: Cell) -> CellState:
    return CellState(
        cell.get_index(),
        cell.is_output_voltage_enabled(),
        cell.get_output_voltage(),
        cell.get_measured_voltage(),
        cell.get_measured_current(),
        cell.get_current_limit(),
        cell.get_ramp_up_speed(),
        cell.get_ramp_down_speed(),
        cell.get_current_limit_range(),
        cell.get_output_voltage_range())


def _read_device_status(device: Device) -> DeviceState:
    return DeviceState(list(map(_read_cell_status, device.cells)))


def _set_output_enabled(cell: Cell, value: bool) -> bool:
    cell.set_output_voltage_enabled(value)
    return cell.is_output_voltage_enabled()


def _set_voltage(cell: Cell, value: float) -> float:
    cell.set_output_voltage(value)
    return cell.get_output_voltage()


def _set_current_limit(cell: Cell, value: float) -> float:
    cell.set_current_limit(value)
    return cell.get_current_limit()


def _set_ramp_up_speed(cell: Cell, value: int) -> int:
    cell.set_ramp_up_speed(value)
    return cell.get_ramp_up_speed()


def _set_ramp_down_speed(cell: Cell, value: int) -> int:
    cell.set_ramp_down_speed(value)
    return cell.get_ramp_down_speed()


class Worker:
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1)
        self.device: Optional[Device] = None
        self._connected = False

    def is_connected(self):
        return self._connected

    def connect(self, device: DeviceAddress) -> Future:
        def _connect():
            logger.info(f"Connecting to device {device}")
            self.device = Device(device.name, CHANNEL_COUNT, device.address, SOCKET_TIMEOUT)
            self._connected = True

        return self._executor.submit(_connect)

    def _read_state(self):
        return _read_device_status(self.device)

    def read_state(self) -> 'Future[DeviceState]':
        return self._executor.submit(self._read_state)

    def set_output_enabled(self, cell: int, enabled: float) -> 'Future[bool]':
        return self._executor.submit(_set_output_enabled, self.device.cells[cell], enabled)

    def set_voltage(self, cell: int, voltage: float) -> 'Future[float]':
        return self._executor.submit(_set_voltage, self.device.cells[cell], voltage)

    def set_current_limit(self, cell: int, value: float) -> 'Future[float]':
        return self._executor.submit(_set_current_limit, self.device.cells[cell], value)

    def set_ramp_up_speed(self, cell: int, value: int) -> 'Future[int]':
        return self._executor.submit(_set_ramp_up_speed, self.device.cells[cell], value)

    def set_ramp_down_speed(self, cell: int, value: int) -> 'Future[int]':
        return self._executor.submit(_set_ramp_down_speed, self.device.cells[cell], value)

    def _disconnect(self):
        self.device.close()

    def shutdown(self) -> Future:
        f = self._executor.submit(self._disconnect)
        self._executor.shutdown(False)
        self._executor = None
        self._connected = False
        return f
