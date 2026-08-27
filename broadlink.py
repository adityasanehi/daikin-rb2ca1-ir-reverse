"""Decode Broadlink b64 -> timings, using the exact python-broadlink algorithm.

Format (python-broadlink remote.py):
  byte 0    : 0x26 (IR)
  bytes 2-3 : encoded body length, little-endian
  body      : per pulse: value = us // 32.84; if >= 256 emit 0x00 + value//256,
              then always value % 256
"""

import base64

TICK = 32.84


def data_to_pulses(data: bytes, tick: float = TICK) -> list[int]:
    result = []
    index = 4
    end = min(256 * data[3] + data[2] + 4, len(data))
    while index < end:
        chunk = data[index]
        index += 1
        if chunk == 0:
            chunk = 256 * data[index] + data[index + 1]
            index += 2
        result.append(int(chunk * tick))
    return result


def pulses_to_data(pulses: list[int], tick: float = TICK) -> bytes:
    result = bytearray(4)
    result[0] = 0x26
    for pulse in pulses:
        div, mod = divmod(int(pulse // tick), 256)
        if div:
            result.append(0)
            result.append(div)
        result.append(mod)
    data_len = len(result) - 4
    result[2] = data_len & 0xFF
    result[3] = data_len >> 8
    return bytes(result)


def decode(b64: str) -> list[int]:
    data = base64.b64decode(b64)
    if data[0] != 0x26:
        raise ValueError("not an IR packet")
    return data_to_pulses(data)


def encode(pulses: list[int]) -> str:
    return base64.b64encode(pulses_to_data(pulses)).decode()
