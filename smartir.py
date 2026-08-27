"""Generate a SmartIR climate profile for the Daikin RB2CA1 protocol.

Writes smartir.json. Copy to <config>/custom_components/smartir/codes/climate/
<device_code>.json on the HA box (device_code: 9001) — see README.

Includes swing: swingModes off/vertical/horizontal/both map to b4 bit0/bit4.
"both" (b4=0x11) and turbo+swing combos are generated (checksum-valid) but
were never captured — the remote clears powerful when swing is pressed.
"""

import json

from daikin import FANS, TEMPS, build_frame, decode_state, from_broadlink, to_broadlink

DEVICE_CODE = 9001
SWINGS = {"off": (False, False), "vertical": (True, False),
          "horizontal": (False, True), "both": (True, True)}


def build_profile() -> dict:
    cool = {}
    for fan in FANS:
        cool[fan] = {}
        for swing, (sv, sh) in SWINGS.items():
            cool[fan][swing] = {
                str(t): to_broadlink(
                    build_frame(t, fan, turbo=fan == "turbo", swing_v=sv, swing_h=sh))
                for t in TEMPS
            }
    return {
        "manufacturer": "Daikin",
        "supportedModels": ["FTKZ50UV16U4", "RB2CA1 remote (India)"],
        "supportedController": "Broadlink",
        "commandsEncoding": "Base64",
        "minTemperature": 18.0,
        "maxTemperature": 30.0,
        "precision": 1.0,
        "operationModes": ["cool"],
        "fanModes": list(FANS),  # auto, 1..5, turbo
        "swingModes": list(SWINGS),
        "commands": {
            # byte-identical to the user-verified power_off learn
            "off": to_broadlink(build_frame(24, "5", power=False, turbo=True, swing_v=True)),
            "cool": cool,
        },
    }


if __name__ == "__main__":
    p = build_profile()
    # validate: every code decodes back to its intended state
    for fan in FANS:
        for swing, (sv, sh) in SWINGS.items():
            for t in TEMPS:
                st = decode_state(from_broadlink(p["commands"]["cool"][fan][swing][str(t)]))
                assert st == {
                    "temp": t, "fan": "5" if fan == "turbo" else fan,
                    "power": True, "turbo": fan == "turbo",
                    "swing_v": sv, "swing_h": sh, "checksum_ok": True,
                }, (fan, swing, t, st)
    assert decode_state(from_broadlink(p["commands"]["off"]))["power"] is False
    assert set(p["commands"]["cool"]) == set(p["fanModes"])
    assert set(p["commands"]["cool"]["auto"]) == set(p["swingModes"])
    json.dump(p, open("smartir.json", "w"), indent=1)
    print(f"wrote smartir.json: {len(FANS)} fans x {len(SWINGS)} swing modes x"
          f" {len(TEMPS)} temps + off, all validated")
