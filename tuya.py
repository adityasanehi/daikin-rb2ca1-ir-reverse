"""Generate a Tuya/MQTT SmartIR profile without changing the Broadlink one."""

import base64
import json
from math import ceil
from struct import pack

from smartir import build_profile

BROADLINK_UNIT = 269 / 8192


def decode_literal_stream(data: bytes) -> bytes:
    raw = bytearray()
    index = 0
    while index < len(data):
        length = data[index] + 1
        index += 1
        if index + length > len(data):
            raise ValueError("truncated Tuya literal block")
        raw.extend(data[index:index + length])
        index += length
    return bytes(raw)


def encode_ir(command: str) -> str:
    data = base64.b64decode(command, validate=True)
    if len(data) < 4 or data[0] != 0x26:
        raise ValueError("not a Broadlink IR packet")

    end = 4 + int.from_bytes(data[2:4], "little")
    if end > len(data):
        raise ValueError("truncated Broadlink IR packet")

    timings = []
    index = 4
    while index < end:
        value = data[index]
        index += 1
        if value == 0:
            if index + 2 > end:
                raise ValueError("truncated Broadlink timing")
            value = int.from_bytes(data[index:index + 2], "big")
            index += 2
        timing = ceil(value / BROADLINK_UNIT)
        if timing < 65535:  # Tuya uint16; discard Broadlink's trailing gap.
            timings.append(timing)

    raw = b"".join(pack("<H", timing) for timing in timings)
    encoded = b"".join(bytes([len(chunk) - 1]) + chunk
                       for start in range(0, len(raw), 32)
                       if (chunk := raw[start:start + 32]))
    assert decode_literal_stream(encoded) == raw
    return base64.b64encode(encoded).decode()


def convert(value):
    if isinstance(value, str):
        return encode_ir(value)
    if isinstance(value, dict):
        return {key: convert(child) for key, child in value.items()}
    return value


if __name__ == "__main__":
    profile = build_profile()
    profile["commands"] = convert(profile["commands"])
    profile["supportedController"] = "MQTT"
    profile["commandsEncoding"] = "Raw"
    with open("smartir_tuya.json", "w") as output:
        json.dump(profile, output, indent=1)
    print("wrote smartir_tuya.json (original Broadlink files unchanged)")
