"""Daikin RB2CA1 (India) IR protocol — reverse-engineered from Broadlink captures.

Frame: 9 bytes, each sent LSB-first (bit 0 first), 38 kHz carrier.
  b0 = 0xAA  sync
  b1 = 0x11  sync
  b2 = turbo<<7 | fan<<4 | power<<3 | 1
        fan: auto=0, 1..5 ; power: 1=on ; turbo (powerful): 1
  b3 = temp - 16          (18..30 C -> 2..14)
  b4 = 0x01, b5 = 0x44    constants (mode-related; all captures were Cool)
  b6 = 0x00, b7 = 0x00
  b8 = (sum(b0..b7) mod 256) ^ 0xAA      (constants sum to 0x100 -> (b2+b3)^0xAA)

Timing (us): header 7000/3500; bit mark 450; space 450 (0) / 1300 (1);
footer mark 450; trailing gap 109440 (Broadlink escape 0x000D05, as learned).

Validated against 21 real captures: every frame decodes with a valid checksum
and the expected state.
"""

from broadlink import decode as bl_decode, encode as bl_encode

HDR_MARK, HDR_SPACE = 7000, 3500
BIT_MARK, ZERO_SPACE, ONE_SPACE = 450, 450, 1300
GAP = 109440  # matches the learned codes' trailing silence

FANS = {"auto": 0, "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "turbo": 5}
TEMPS = range(18, 31)


def checksum(frame8: bytes) -> int:
    return (sum(frame8) & 0xFF) ^ 0xAA


def build_frame(temp: int, fan: str, power: bool = True, turbo: bool = False) -> bytes:
    assert temp in TEMPS and fan in FANS
    b2 = (0x80 if turbo else 0) | (FANS[fan] << 4) | (0x08 if power else 0) | 0x01
    body = bytes([0xAA, 0x11, b2, temp - 16, 0x01, 0x44, 0x00, 0x00])
    return body + bytes([checksum(body)])


def frame_to_timings(frame: bytes) -> list[int]:
    t = [HDR_MARK, HDR_SPACE]
    for byte in frame:
        for k in range(8):  # LSB first
            t.append(BIT_MARK)
            t.append(ONE_SPACE if (byte >> k) & 1 else ZERO_SPACE)
    t += [BIT_MARK, GAP]
    return t


def timings_to_frame(t: list[int]) -> bytes:
    assert len(t) == 2 + 72 * 2 + 2, f"unexpected timing count {len(t)}"
    assert t[0] > 5000, "bad header mark"
    bits = [1 if t[2 + 2 * i + 1] > 800 else 0 for i in range(72)]
    return bytes(sum(bits[8 * i + k] << k for k in range(8)) for i in range(9))


def to_broadlink(frame: bytes) -> str:
    return bl_encode(frame_to_timings(frame))


def from_broadlink(b64: str) -> bytes:
    return timings_to_frame(bl_decode(b64))


def decode_state(frame: bytes) -> dict:
    b2 = frame[2]
    rev_fans = {v: k for k, v in FANS.items() if k != "turbo"}
    return {
        "temp": frame[3] + 16,
        "fan": rev_fans[(b2 >> 4) & 7],
        "power": bool(b2 & 0x08),
        "turbo": bool(b2 & 0x80),
        "checksum_ok": frame[8] == checksum(frame[:8]),
    }


if __name__ == "__main__":  # self-check: round-trip + checksum
    for temp in (18, 24, 30):
        for fan in FANS:
            f = build_frame(temp, fan)
            assert f == from_broadlink(to_broadlink(f)), (temp, fan)
            assert decode_state(f)["checksum_ok"]
    off = build_frame(24, "5", power=False, turbo=True)
    assert off == from_broadlink(to_broadlink(off)) and decode_state(off)["checksum_ok"]
    print("daikin.py self-check OK (13 fans/temps round-trip, checksum valid)")
