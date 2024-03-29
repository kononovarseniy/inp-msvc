import logging
import socket
from dataclasses import dataclass
from typing import Union, Optional, Tuple, Dict

from device.command import Command, CommandType, CommandResponse, encode_command, RESPONSE_LENGTH, decode_response
from device.helpers import code_to_float, float_to_code
from device.registers import CellRegister, ControllerRegister, CellCSR, ControllerSR, TemperatureSensor

LOGGER = logging.getLogger("device")

MAX_CURRENT_DAC_CODE = (1 << 10) - 1
MAX_CURRENT_ADC_CODE = (1 << 12) - 1

MAX_DAC_CODE = (1 << 12) - 1
MAX_ADC_CODE = (1 << 12) - 1


class DeviceSocket:
    def __init__(self, address: Union[tuple, str, bytes], timeout: Optional[float]):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(timeout)
        self.socket.connect(address)

    def send_command(self, command: Command) -> CommandResponse:
        data = encode_command(command).encode()
        self.socket.sendall(data)
        recv = RESPONSE_LENGTH
        buf = bytearray(RESPONSE_LENGTH)
        while recv > 0:
            res = self.socket.recv_into(buf, recv)
            if res == 0:
                raise EOFError('Remote device closed connection')
            recv -= res
        return decode_response(buf.decode())

    def close(self):
        self.socket.close()


class RegisterProvider:
    def __init__(self, cell: int, name: str, sock: DeviceSocket):
        self.cell = cell
        self.name = name
        self._cache: Dict[int, int] = dict()
        self._socket: DeviceSocket = sock

    def write(self, register: int, data: int) -> int:
        cmd = Command(CommandType.WRITE, self.cell, register, data, True)
        resp = self._socket.send_command(cmd)
        if not resp.is_crc_ok:
            LOGGER.warning(f'Writing register {repr(register)} of {self.name}: bad CRC')

        self._cache[register] = data
        return resp.data

    def read(self, register: int) -> int:
        cmd = Command(CommandType.READ, self.cell, register, 0, True)
        resp = self._socket.send_command(cmd)
        if not resp.is_crc_ok:
            LOGGER.warning(f'Reading register {repr(register)} of {self.name}: bad CRC')

        self._cache[register] = resp.data
        return resp.data

    def read_cached(self, register: int) -> int:
        if register in self._cache:
            return self._cache[register]
        return self.read(register)

    def invalidate_cache(self):
        self._cache.clear()


class Controller:
    def __init__(self, name: str, sock: DeviceSocket):
        self.name = name
        self.registers = RegisterProvider(0, name, sock)

    def write(self, register: ControllerRegister, value: int) -> int:
        return self.registers.write(int(register), value)

    def read(self, register: ControllerRegister) -> int:
        return self.registers.read(int(register))

    def read_cached(self, register: ControllerRegister) -> int:
        return self.registers.read_cached(int(register))

    def invalidate_cache(self):
        self.registers.invalidate_cache()

    def get_status(self) -> ControllerSR:
        return ControllerSR(self.registers.read(ControllerRegister.status))

    def set_base_voltage_enabled(self, enabled: bool) -> bool:
        return self.registers.write(ControllerRegister.BVON, 1 if enabled else 0) != 0

    def get_base_voltage_enabled(self) -> bool:
        return self.registers.read(ControllerRegister.BVON) != 0

    def get_processor_temperature(self) -> int:
        return self.registers.read(ControllerRegister.Tup)

    def get_board_temperature(self) -> int:
        return self.registers.read(ControllerRegister.Tbrd)

    def get_power_supply_temperature(self) -> int:
        return self.registers.read(ControllerRegister.Tps)

    def get_low_voltage(self) -> float:
        return self.registers.read(ControllerRegister.LV) / 10

    def get_base_voltage(self) -> float:
        return self.registers.read(ControllerRegister.BV) / 10

    def set_fan_off_temperature(self, value: int) -> int:
        return self.registers.write(ControllerRegister.T_fan_off, value)

    def get_fan_off_temperature(self) -> int:
        return self.registers.read(ControllerRegister.T_fan_off)

    def set_fan_on_temperature(self, value: int) -> int:
        return self.registers.write(ControllerRegister.T_fan_on, value)

    def get_fan_on_temperature(self) -> int:
        return self.registers.read(ControllerRegister.T_fan_on)

    def set_shutdown_temperature(self, value: int) -> int:
        return self.registers.write(ControllerRegister.T_shutdown, value)

    def get_shutdown_temperature(self) -> int:
        return self.registers.read(ControllerRegister.T_shutdown)

    def set_temperature_sensor(self, sensor: TemperatureSensor):
        return TemperatureSensor(self.registers.write(ControllerRegister.NTsens, sensor))

    def get_temperature_sensor(self) -> TemperatureSensor:
        return TemperatureSensor(self.registers.read(ControllerRegister.NTsens))

    def get_serial(self) -> int:
        return self.registers.read(ControllerRegister.CserNr)


class Cell:
    def __init__(self, cell: int, name: str, sock: DeviceSocket):
        self.name = name
        self._cell = cell
        self.registers = RegisterProvider(cell, name, sock)

    def write(self, register: CellRegister, value: int) -> int:
        return self.registers.write(int(register), value)

    def read(self, register: CellRegister) -> int:
        return self.registers.read(int(register))

    def read_cached(self, register: CellRegister) -> int:
        return self.registers.read_cached(int(register))

    def invalidate_cache(self):
        self.registers.invalidate_cache()

    def get_index(self) -> int:
        """Cell index, numbering from one"""
        return self._cell

    def get_csr(self) -> CellCSR:
        return CellCSR(self.registers.read(CellRegister.ctl_stat))

    def get_measured_voltage_range(self) -> Tuple[float, float]:
        return 0, self.registers.read_cached(CellRegister.Umesmax)

    def get_measured_voltage(self) -> float:
        adc = self.registers.read(CellRegister.Vmes)
        adc_max = self.registers.read_cached(CellRegister.Umesmax)
        if adc > MAX_ADC_CODE:
            LOGGER.warning(f'{self.name}: Invalid measured voltage ADC code {adc}')
        return code_to_float(adc, MAX_ADC_CODE, 0, adc_max)

    def get_measured_current_range(self) -> Tuple[float, float]:
        return 0, self.registers.read_cached(CellRegister.Imesmax)

    def get_measured_current(self) -> float:
        adc = self.registers.read(CellRegister.Imes)
        adc_max = self.registers.read_cached(CellRegister.Imesmax)
        if adc > MAX_CURRENT_ADC_CODE:
            LOGGER.warning(f'{self.name}: Invalid measured current ADC code {adc}')
        return code_to_float(adc, MAX_CURRENT_ADC_CODE, 0, adc_max)

    def get_current_limit_range(self) -> Tuple[float, float]:
        return 0, self.registers.read_cached(CellRegister.Imax)

    def set_current_limit(self, limit: float) -> float:
        r_min, r_max = self.get_current_limit_range()

        if limit > r_max or limit < r_min:
            LOGGER.warning(
                f'Attempt to set current limit of {self.name} to {limit} uA, '
                f'but allowed range is {r_min}-{r_max}uA')
            raise ValueError('Current limit is out of range')
        code = float_to_code(limit, MAX_CURRENT_DAC_CODE, r_min, r_max)
        code = self.registers.write(CellRegister.Iset, code)
        if code > MAX_CURRENT_DAC_CODE:
            LOGGER.warning(f'{self.name}: Invalid current limit DAC code {code}')
        return code_to_float(code, MAX_CURRENT_DAC_CODE, r_min, r_max)

    def get_current_limit(self) -> float:
        r_min, r_max = self.get_current_limit_range()
        code = self.registers.read(CellRegister.Iset)
        if code > MAX_CURRENT_DAC_CODE:
            LOGGER.warning(f'{self.name}: Invalid current limit DAC code {code}')
        return code_to_float(code, MAX_CURRENT_DAC_CODE, r_min, r_max)

    def get_output_voltage_range(self) -> Tuple[float, float]:
        return self.registers.read_cached(CellRegister.Umin), \
               self.registers.read_cached(CellRegister.Umax)

    def set_output_voltage(self, voltage: float) -> float:
        r_min, r_max = self.get_output_voltage_range()

        if voltage > r_max or voltage < r_min:
            LOGGER.warning(
                f'Attempt to set voltage of {self.name} to {voltage}V, '
                f'but allowed range is {r_min}-{r_max}V')
            raise ValueError('Voltage is out of range')
        code = float_to_code(voltage, MAX_DAC_CODE, r_min, r_max)
        code = self.registers.write(CellRegister.VsetON, code)
        if code > MAX_DAC_CODE:
            LOGGER.warning(f'{self.name}: Invalid output voltage DAC code {code}')
        return code_to_float(code, MAX_DAC_CODE, r_min, r_max)

    def get_output_voltage(self) -> float:
        r_min, r_max = self.get_output_voltage_range()
        code = self.registers.read(CellRegister.VsetON)
        if code > MAX_DAC_CODE:
            LOGGER.warning(f'{self.name}: Invalid output voltage DAC code {code}')
        return code_to_float(code, MAX_DAC_CODE, r_min, r_max)

    def set_output_voltage_enabled(self, enabled: bool) -> bool:
        val = self.registers.read(CellRegister.ctl_stat)
        val &= ~1
        val |= int(enabled)
        resp = self.registers.write(CellRegister.ctl_stat, val)
        return bool(CellCSR(resp).channel_on_state)

    def is_output_voltage_enabled(self) -> bool:
        val = self.registers.read(CellRegister.ctl_stat)
        return bool(val & 1)

    def set_ramp_up_speed(self, speed: float) -> int:
        return self.registers.write(CellRegister.rupspeed, int(speed))

    def get_ramp_up_speed(self) -> int:
        return self.registers.read(CellRegister.rupspeed)

    def set_ramp_down_speed(self, speed: float) -> int:
        return self.registers.write(CellRegister.rdwnspeed, int(speed))

    def get_ramp_down_speed(self) -> int:
        return self.registers.read(CellRegister.rdwnspeed)


@dataclass(eq=True, frozen=True)
class DeviceAddress:
    name: str
    address: Tuple[str, int]

    def __str__(self) -> str:
        return f"{self.name}@{self.address[0]}:{self.address[1]}"


class Device:
    def __init__(self, address: DeviceAddress, cell_count: int, timeout: Optional[float]):
        self.address = address

        sock = DeviceSocket(address.address, timeout)

        self.controller = Controller(address.name, sock)
        """Controller of the device. It contains device global registers"""

        self.cells = [Cell(i + 1, f'{address.name}#{i + 1}', sock) for i in range(cell_count)]
        """
        Channels of the device.
        Here cells are indexed starting from 0, but in device they are numbered starting from 1.
        """

        self._socket = sock

    def __str__(self):
        return f'<Device {self.address}>'

    def invalidate_cache(self):
        self.controller.invalidate_cache()
        for c in self.cells:
            c.invalidate_cache()

    def close(self):
        self._socket.close()
        self._socket = None
        self.controller = None
        self.cells = None
