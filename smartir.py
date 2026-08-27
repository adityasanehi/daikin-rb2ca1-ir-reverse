"""Generate a SmartIR climate profile for the Daikin RB2CA1 protocol.

Writes 9001.json (SmartIR codes file). Custom files live in
<config>/smartir/codes/climate/<device_code>.json on the HA box.

Swing: not yet reverse-engineered. When swing captures arrive, add a
"swingModes" list and an extra nesting level commands[mode][fan][swing][temp].
"""

import json

from daikin import FANS, TEMPS, build_frame, decode_state, from_broadlink, to_broadlink

DEVICE_CODE = 9001


def build_profile() -> dict:
    cool = {}
    for fan in FANS:
        cool[fan] = {
            str(t): to_broadlink(build_frame(t, fan, turbo=fan == "turbo"))
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
        "commands": {
            "off": to_broadlink(build_frame(24, "5", power=False, turbo=True)),
            "cool": cool,
        },
    }


if __name__ == "__main__":
    p = build_profile()
    # validate: every code decodes back to its intended state
    for fan in FANS:
        for t in TEMPS:
            st = decode_state(from_broadlink(p["commands"]["cool"][fan][str(t)]))
            assert st == {
                "temp": t, "fan": "5" if fan == "turbo" else fan,
                "power": True, "turbo": fan == "turbo", "checksum_ok": True,
            }, (fan, t, st)
    assert decode_state(from_broadlink(p["commands"]["off"]))["power"] is False
    assert set(p["commands"]["cool"]) == set(p["fanModes"])
    out = f"{DEVICE_CODE}.json"
    json.dump(p, open(out, "w"), indent=1)
    print(f"wrote {out}: {len(FANS)} fan modes x {len(TEMPS)} temps + off, all validated")
