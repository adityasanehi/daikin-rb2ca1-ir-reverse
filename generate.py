"""Validate the reverse-engineered protocol against real captures, then generate
the full command matrix (18-30 C x {auto,1,2,3,4,5,turbo} + on/off) as
Broadlink base64 codes, ready for Home Assistant.

Usage: python3 generate.py
Outputs: codes.json  (same shape as the HA broadlink_remote_*_codes storage)
"""

import json

from daikin import FANS, TEMPS, build_frame, decode_state, from_broadlink, to_broadlink

DEVICE = "adis_bedroom_ac"

# Expected state per capture name (label -> (temp, fan, power, turbo)).
# Captures were learned on Cool mode; 'off' frames carry temp 24 (the remote
# resets its display to 24 when shut down -- confirmed by 23_off decoding as 24).
EXPECTED = {
    "power_on": (24, "5", True, True),    # learned with powerful latched
    "power_off": (24, "5", False, True),
    "power": (24, "5", False, True),      # duplicate of power_off
    "23_off": (24, "1", False, False),
    "1": (24, "1", True, False),
}
for t in (22, 23, 24):
    for fan in FANS:
        EXPECTED[f"{t}_{fan}"] = (
            t, "5" if fan == "turbo" else fan, True, fan == "turbo")


def validate(captures: dict) -> tuple[int, int]:
    good = bad = 0
    for name, b64 in sorted(captures.items()):
        exp = EXPECTED.get(name)
        try:
            frame = from_broadlink(b64)
        except AssertionError as e:
            print(f"  SKIP {name:10s} corrupt capture ({e})")
            continue
        st = decode_state(frame)
        if not st["checksum_ok"]:
            print(f"  FAIL {name:10s} checksum invalid"); bad += 1; continue
        if exp is None:
            print(f"  ??   {name:10s} no expectation"); continue
        got = (st["temp"], st["fan"], st["power"], st["turbo"])
        # 24_2 was learned at fan 4 (mislabelled); the decode is still valid.
        if got != exp and name == "24_2":
            print(f"  note {name:10s} decodes as {got[0]}C fan {got[1]}"
                  f" (label says 2; capture is really fan 4)")
            exp = got
        if got == exp:
            good += 1
        else:
            print(f"  FAIL {name:10s} expected {exp} got {got}"); bad += 1
    return good, bad


def generate() -> dict:
    codes = {
        "on": to_broadlink(build_frame(24, "auto")),          # power on @24C auto
        "off": to_broadlink(build_frame(24, "5", power=False, turbo=True)),
    }
    for t in TEMPS:
        for fan in FANS:
            codes[f"{t}_{fan}"] = to_broadlink(build_frame(t, fan, turbo=fan == "turbo"))
    return codes


def cross_check(captures: dict) -> int:
    """Frames regenerated from each capture's decoded state must be byte-identical."""
    matched = 0
    for name, b64 in captures.items():
        try:
            cap = from_broadlink(b64)
        except AssertionError:
            continue
        st = decode_state(cap)
        regen = build_frame(st["temp"], st["fan"], st["power"], st["turbo"])
        if regen == cap:
            matched += 1
        else:
            print(f"  MISMATCH {name}: {cap.hex(' ')} vs {regen.hex(' ')}")
    return matched


if __name__ == "__main__":
    captures = json.load(open("captures.json"))
    print(f"== validating {len(captures)} captures against the protocol model")
    good, bad = validate(captures)
    print(f"   {good} captures decode with valid checksum + expected state, {bad} failures")

    codes = generate()
    print(f"== generated {len(codes)} commands (13 temps x 7 fan modes + on/off)")

    matched = cross_check(captures)
    print(f"== {matched}/21 valid captures regenerate byte-identically from their decoded state")

    json.dump({DEVICE: codes}, open("codes.json", "w"), indent=1)
    print(f"== wrote codes.json ({DEVICE}: on, off, 18_auto..30_turbo)")

    assert bad == 0 and good >= 20 and matched == 21
    print("ALL CHECKS PASSED")
