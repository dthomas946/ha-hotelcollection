# Hotel Collection for Home Assistant

*Created with Claude.ai.*

Local, cloud-free Home Assistant control of **Hotel Collection** scent diffusers —
verified on the **Villa 2.0** — that pair with the *ScentArea* app.

The diffuser keeps a plain TCP control port open on your network (**8080**).
This integration talks to that port directly: no cloud, no account, and the
ScentArea app keeps working alongside it.

Other white-label diffusers that use the ScentArea app (for example some
Aroma360 2.0 models) likely speak the same protocol but are untested.

## What you get

| Entity | Type | Notes |
|---|---|---|
| Scent | switch | Your on/off; with the HVAC pause, the integration runs the pump while this is on |
| Scent status | sensor | Spraying · Starting · Paused: HVAC fan off · Outside schedule · Off |
| Power | switch | The pump itself. Instant; changes made in the app show up immediately |
| Fan | switch | |
| Child lock | switch (config) | |
| Oil remaining | sensor, mL | From the device |
| Oil level | sensor, % | Remaining ÷ bottle size |
| Bottle size | sensor, mL (diagnostic) | |
| Consumption rate | sensor, mL/h | mL used per hour of *spraying* — a calibration value for the oil gauge, not a strength setting |
| Spraying time left | sensor, h | Remaining ÷ rate — hours of spraying, not calendar time |
| Oil days left | sensor, days | The diffuser's own estimate at the current schedule |
| Consumption rate setting | number, mL/h | Edit to calibrate the gauge (0.1–25.5) |
| Oil remaining setting | number, mL | Correct the level after measuring the bottle |
| Bottle size setting | number, mL (config) | |
| Oil to fill | sensor, mL | Room left below the 90 % max-fill line (fl oz in attributes) — how much to order |
| Add oil | button | Adds *Oil to add* to oil remaining (capped at the bottle size) and starts a new calibration baseline |
| Oil to add | number | How much you pour in per refill (default 500 mL) |
| Spray time since refill | sensor | Hours the pump actually sprayed since the last refill |
| Level at last refill / Measured oil level | number | Calibration inputs |
| Calibrate rate | button | Sets the consumption rate (and oil remaining) from the measured level |
| Active schedule slots | sensor | Full slot list (days, times, work/pause) in attributes |
| Device clock | sensor (diagnostic, off by default) | |
| Scent | text | Kept in HA — the diffuser does not store the scent name |

## HVAC pause (for diffusers that feed a duct)

When the diffuser is connected to your HVAC ductwork, mist only reaches the house
while the HVAC blower moves air; otherwise it settles in the ducts. Turn on the HVAC
pause in **Settings → Devices & services → Hotel Collection → Configure** and pick the
entity that shows the fan is running — a thermostat (`hvac_action` heating / cooling /
fan, or `fan_action: on`), a blower sensor (> 0) or a switch/binary sensor.

The diffuser then runs only when all three are true:

| HVAC fan running | A mode scheduled now | **Scent** switch on | → Diffuser |
|---|---|---|---|
| yes | yes | yes | on (after a start delay, default 20 s) |
| no | | | off, straight away |
| | no | | off |
| | | no | off |

**You stay in control:** turning the diffuser off anywhere — the Scent switch, the
Power switch, the ScentArea app or the button on the unit — turns Scent off, and the
HVAC pause leaves it off until you turn Scent back on. *Scent status* shows why the
diffuser is or isn't spraying.

## Oil calibration

The Villa never measures its oil. It takes the level you last gave it and subtracts
*consumption rate × hours of spraying* (mode time × spray ÷ (spray + pause)), so
the level is only as good as the rate. The integration counts the spraying hours
since the last refill (power on, inside an enabled mode, weighted by that mode's
spray share), so you can correct the rate:

1. When you refill, press **Add oil** (or call `hotelcollection.record_refill`
   with the level and time, for a refill you forgot to log).
2. Some days later, read the real level off the bottle and enter it in
   **Measured oil level**. *Spray time since refill* shows the preview rate.
3. Press **Calibrate rate**: the rate becomes
   `(level at refill − measured) ÷ spraying hours`, and oil remaining becomes the
   measured level. It needs at least 5 hours of spraying (about a week on the
   current schedule is better); longer is more accurate.

## Dashboard card

The integration ships a card and loads it automatically (no resource to add):

```yaml
type: custom:hotelcollection-card
device: villa   # entity prefix: switch.villa_power, sensor.villa_oil_level, …
name: Villa     # optional
```

It shows the five modes on a weekly 24-hour timeline with a marker for now, which mode
is running (or the next one), the scent, oil level and hours of spraying left, plus
power and fan buttons. Below the timeline each mode has an on/off switch; tap a mode
(its bar or its row) to edit days, start and end time, spray seconds and pause seconds.

## Action: `hotelcollection.set_mode`

Change one schedule mode from automations or scripts. Fields you leave out keep their
current value.

```yaml
action: hotelcollection.set_mode
data:
  mode: 5                 # 1-5
  enabled: true
  days: [Sat, Sun]
  start: "20:00"
  end: "23:59"
  spray_seconds: 70
  pause_seconds: 90
```

![Card](docs/images/card.png)

## Install

1. Give the diffuser a fixed IP (DHCP reservation) in your router.
2. HACS → ⋮ → **Custom repositories** → add `https://github.com/dthomas946/ha-hotelcollection`, category **Integration**.
3. Download **Hotel Collection**, restart Home Assistant.
4. Settings → Devices & services → **Add integration** → *Hotel Collection* → enter the IP.

If you use firewall groups/VLANs, allow Home Assistant → diffuser on TCP 8080.

## Not yet supported

- Editing the schedule (read-only for now; edit it in the ScentArea app).
- Unknown value: cmd `0B`.

### How much you smell

Scent strength comes from the **spray** and **pause** seconds in each mode, plus how
long the modes run. From the ScentArea-family manual (DaVinci360 2.0):

- Spray and pause each range **5–300 s**; use at least **15 s** of spray so the diffuser can
  draw and atomize the oil.
- A mode **cannot run past midnight** — end at 23:59 and start another mode at 00:00.
- Suggested ceilings for a bottle to last about a month: 500 mL → up to 60 h/week at
  90 s spray / 110 s pause (200 mL → 50 h at 110/90; 1 L → 65 h at 80/120).
- The diffuser's **Fan** switch runs its built-in blower, which spreads mist into the room
  the diffuser sits in. Leave it **on** for standalone use; turn it **off** when the diffuser
  feeds an HVAC duct, or the scent stays in the room where the unit is (an attic, a closet).
- When HVAC-connected, the **HVAC blower** must be running while the diffuser sprays, or
  the mist settles in the ductwork.

The integration enforces the first two rules. The consumption rate only tells the diffuser how fast oil is used
so it can estimate what's left. To calibrate it, note the oil level, let it run about
10 days, measure the bottle, then adjust the rate until *Oil remaining* matches.

## If Home Assistant drops off

You can use the ScentArea app (Wi-Fi or AP mode) alongside this integration; changes
made in the app show up in Home Assistant right away. Rarely, the diffuser stops
accepting Home Assistant's connection (seen once while saving in the app). If the
entities stay unavailable for more than a couple of minutes, unplug the diffuser for
10 seconds; Home Assistant reconnects on its own.

## ⚠️ Don't port-scan with version detection

`nmap -sV` against port 8080 sends junk that the diffuser accepts as commands —
it flipped settings during development, and a burst of quick test connections
later made it refuse local connections until it was power-cycled. Plain port
scans are fine.

## Protocol

See [docs/protocol.md](docs/protocol.md). The codec is pure Python
(`custom_components/hotelcollection/codec.py`) and tested against real captures
(`tests/test_codec.py`).

## Credits

Created by [@dthomas946](https://github.com/dthomas946) with **Claude (claude.ai)** by Anthropic —
protocol reverse-engineering, codec, tests and integration were built together
in a Claude.ai session in November 2026.

Not affiliated with Hotel Collection, ScentArea or Aroma360.
