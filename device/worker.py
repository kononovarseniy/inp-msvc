import logging
from concurrent.futures import Future
from concurrent.futures.thread import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Iterable, Tuple, List

from device.device import Device, Cell

CHANNEL_COUNT = 16

SOCKET_TIMEOUT = 10

logger = logging.getLogger("Worker")
logger.setLevel(logging.INFO)


@dataclass
class DeviceInfo:
    name: str
    address: Tuple[str, int]


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
        self.devices: List[Device] = []

    def connect(self, devices: Iterable[DeviceInfo]) -> Future:
        ds = list(devices)

        def _connect():
            logger.info("Connecting to devices...")
            for i, dev in enumerate(ds):
                logger.info(f"Connecting to device #{i + 1} {dev.address}")
                self.devices.append(Device(dev.name, CHANNEL_COUNT, dev.address, SOCKET_TIMEOUT))

        return self._executor.submit(_connect)

    def _read_state(self):
        return list(map(_read_device_status, self.devices))

    def read_state(self) -> 'Future[List[DeviceState]]':
        return self._executor.submit(self._read_state)

    def set_output_enabled(self, device: int, cell: int, enabled: float) -> 'Future[bool]':
        return self._executor.submit(_set_output_enabled, self.devices[device].cells[cell], enabled)

    def set_voltage(self, device: int, cell: int, voltage: float) -> 'Future[float]':
        return self._executor.submit(_set_voltage, self.devices[device].cells[cell], voltage)

    def set_current_limit(self, device: int, cell: int, value: float) -> 'Future[float]':
        return self._executor.submit(_set_current_limit, self.devices[device].cells[cell], value)

    def set_ramp_up_speed(self, device: int, cell: int, value: int) -> 'Future[int]':
        return self._executor.submit(_set_ramp_up_speed, self.devices[device].cells[cell], value)

    def set_ramp_down_speed(self, device: int, cell: int, value: int) -> 'Future[int]':
        return self._executor.submit(_set_ramp_down_speed, self.devices[device].cells[cell], value)

    def disconnect(self) -> Future:
        ds = self.devices
        self.devices = []

        def _disconnect():
            for d in ds:
                d.close()

        return self._executor.submit(_disconnect)
