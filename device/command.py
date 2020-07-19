from dataclasses import dataclass
from enum import Enum

RESPONSE_LENGTH = 6


class CommandType(Enum):
    READ = 1
    WRITE = 2


@dataclass
class Command:
    command_type: CommandType
    address: int
    sub_address: int
    data: int
    is_crc_ok: bool


@dataclass
class CommandResponse:
    data: int
    is_crc_ok: bool


def get_crc(string: str) -> int:
    s = sum(int(ch, 16) for ch in string)
    return (s ^ 0xf) & 0xf


def encode_command(command: Command) -> str:
    if command.command_type == CommandType.READ:
        cmd = f'r{command.address:02x}{command.sub_address:02x}'
    else:
        cmd = f'w{command.address:02x}{command.sub_address:02x}{command.data:04x}'
    crc = f'{get_crc(cmd[1:]):x}' if command.is_crc_ok else '0'
    return cmd + crc + '\n'


def decode_response(string: str) -> CommandResponse:
    if string[-1] != '\n' or len(string) != RESPONSE_LENGTH:
        raise ValueError('Invalid response format')
    data = int(string[0:4], 16)
    crc_ok = get_crc(string[0:5]) == 0
    return CommandResponse(data, crc_ok)
