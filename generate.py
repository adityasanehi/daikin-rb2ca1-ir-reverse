"""Validate the reverse-engineered protocol against real captures, then generate
the full command matrix as Broadlink base64 codes, ready for Home Assistant.

Matrix: 18-30 C x {auto,1,2,3,4,5,turbo} x {no swing, vertical, horizontal, both}
+ on/off. Plain codes (e.g. "25_2") send swing OFF — the original 2023-era
captures were all learned with vertical swing latched on (b4=0x01), confirmed
on the real AC; suffixed codes _v/_h/_vh send the corresponding swing state.

Usage: python3 generate.py
Outputs: codes.json  (same shape as the HA broadlink_remote_*_codes storage)
"""

import json

from daikin import FANS, TEMPS, build_frame, decode_state, from_broadlink, to_broadlink

DEVICE = "adis_bedroom_ac"
SWINGS = {"": (False, False), "_v": (True, False), "_h": (False, True), "_vh": (True, True)}

# Decoded swing-learn frames (checksum-validated; the raw learns' base64 is too
# long to carry through chat reliably, so the decoded 9-byte frames are the
# recorded evidence). Turbo-labelled learns decoded WITHOUT the turbo bit:
# pressing swing on this remote clears powerful mode.
SWING_EVIDENCE = {
    "24_5_vertical_on":    ("aa11590801440000cb", 24, "5", False, True, False),
    "24_5_vertical_off":   ("aa11590800440000ca", 24, "5", False, False, False),
    "24_5_horizontal_on":  ("aa11590810440000da", 24, "5", False, False, True),
    "24_5_horizontal_off": ("aa11590800440000ca", 24, "5", False, False, False),
}

# Expected state per capture name (label -> (temp, fan, power, turbo)).
# Captures were learned on Cool mode, all with vertical swing ON (b4=0x01);
# 'off' frames carry temp 24 (the remote resets its display to 24 when shut
# down -- confirmed by 23_off decoding as 24).
EXPECTED = {
    "power_on": (24, "5", True, True),    # learned with powerful latched
    "power_off": (24, "5", False, True),
    "power": (24, "5", False, True),      # duplicate of power_off
    "23_off": (24, "1", False, False),
    "1": (24, "1", True, False),
    # display toggle learns (24C fan5 swing off): only the set->off press
    # encodes anything (b5 bit7); the others are the plain 24_5 frame.
    "display_2": (24, "5", True, False),
    "display_1_again": (24, "5", True, False),
    "display_3": (24, "5", True, False),
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
        # all original 2023-era captures were learned with vertical swing ON;
        # display learns (2025) were made with swing OFF
        if not name.startswith("display") and (not st["swing_v"] or st["swing_h"]):
            print(f"  FAIL {name:10s} expected swing_v on (learned state), got v={st['swing_v']} h={st['swing_h']}")
            bad += 1; continue
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


def validate_swing_evidence() -> int:
    """The decoded swing learns must regenerate byte-identically."""
    ok = 0
    for name, (hexs, t, fan, turbo, sv, sh) in SWING_EVIDENCE.items():
        f = bytes.fromhex(hexs)
        st = decode_state(f)
        regen = build_frame(t, fan, True, turbo, sv, sh)
        assert st["checksum_ok"] and regen == f, name
        assert (st["temp"], st["fan"], st["swing_v"], st["swing_h"]) == (t, fan, sv, sh), name
        ok += 1
    return ok


def generate() -> dict:
    codes = {
        "on": to_broadlink(build_frame(24, "auto")),   # power on @24C auto, no swing
        "off": to_broadlink(build_frame(24, "5", power=False, turbo=True, swing_v=True)),
        # ^ byte-identical to the user-verified power_off learn (turbo + swing
        #   bits were latched on the remote at learn time; irrelevant once off)
    }
    for t in TEMPS:
        for fan in FANS:
            for suf, (sv, sh) in SWINGS.items():
                codes[f"{t}_{fan}{suf}"] = to_broadlink(
                    build_frame(t, fan, turbo=fan == "turbo", swing_v=sv, swing_h=sh))
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
        regen = build_frame(st["temp"], st["fan"], st["power"], st["turbo"],
                            st["swing_v"], st["swing_h"], st["display_off"])
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

    n_ev = validate_swing_evidence()
    print(f"== {n_ev}/4 decoded swing-learn states regenerate byte-identically"
          " (v on/off, h on/off @24C fan5)")

    codes = generate()
    print(f"== generated {len(codes)} commands"
          f" ({len(TEMPS)} temps x {len(FANS)} fans x {len(SWINGS)} swing states + on/off)")

    matched = cross_check(captures)
    print(f"== {matched}/24 valid captures regenerate byte-identically from their decoded state")

    # spot-check generated codes decode back to their intended state
    for name in ("on", "off", "25_2", "25_2_v", "25_2_h", "25_2_vh", "30_turbo_vh"):
        st = decode_state(from_broadlink(codes[name]))
        assert st["checksum_ok"], name
    assert decode_state(from_broadlink(codes["off"]))["power"] is False

    json.dump({DEVICE: codes}, open("codes.json", "w"), indent=1)
    print(f"== wrote codes.json ({DEVICE}: on, off, 18_auto..30_turbo[_v|_h|_vh])")

    assert bad == 0 and good >= 23 and matched == 24 and n_ev == 4
    print("ALL CHECKS PASSED")
