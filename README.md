# Hotel Collection for Home Assistant

*Created with Claude.ai.*

Local, cloud-free Home Assistant control of **Hotel Collection** scent diffusers —
verified on the **Villa 2.0** — that pair with the *ScentArea* app.

The diffuser keeps a plain TCP control port open on your network (**8080**).
This integration talks to that port directly: no cloud, no account, and the
ScentArea app keeps working alongside it.

Other white-label diffusers that use the ScentArea app (for example some
Aroma360 2.0 models) likely speak the same protocol but are untested.

> **Setting it up?** Follow **[docs/INSTALL.md](docs/INSTALL.md)**. It covers every
> setting and where to change it, plus a ready-made dashboard page. To let an AI
> assistant do the setup, give it **[docs/AI_SETUP.md](docs/AI_SETUP.md)**.

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
| HVAC fan source | select | Entity that shows the HVAC blower is running (`none` = HVAC pause off); same as **Configure** |
| HVAC start delay | number | Seconds of airflow before spraying; same as **Configure** |
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

## Oil calibration: training the oil level

**Why it matters.** The Villa has no oil sensor. *Oil remaining*, *Oil days left*,
the gauge and the low-oil warning are all worked out the same way: *the level
you last gave it − consumption rate × hours of spraying*. Spraying hours are mode
time × spray ÷ (spray + pause). So every oil number is only as good as the
**consumption rate**, and the rate depends on your oil (thicker oils use less),
your spray/pause settings, and the unit itself. The number on the box or in the
app is only a starting point.

**Calibration is training, not a one-off.** Each refill-to-measurement period is
one training session. It compares the oil actually used with the spraying hours
the integration counted (power on, inside an enabled mode, weighted by that
mode's spray share; time paused by the HVAC pause doesn't count), and it sets the
rate that would have predicted the drop:

> rate = (level at refill − measured level) ÷ spraying hours

Plan on **two or three sessions over a couple of bottles (a few months)**:

| Session | When | What you get |
|---|---|---|
| 1 | First refill → about a week or two later | A rough rate. Small drops are hard to measure, so expect it to move. |
| 2 | Next refill → most of the bottle used | A good rate. A larger drop means a smaller relative error. |
| 3+ | Each later refill, or whenever you change the oil or the spray/pause times | Confirms the rate, or re-trains it for the new oil or settings |

Once two sessions in a row agree within about 0.2 mL/h, the rate is trained.
*Spray time since refill* keeps the last 12 sessions in its
`calibration_history` attribute, so you can compare them.

**Each session:**

1. **At the refill:** set **Oil to add** to what you pour in and press **Add oil**.
   This sets *Level at last refill* and restarts the spraying-hours count. If you
   know the exact level after filling, type it into **Level at last refill**
   instead. (Forgot to log a refill? `hotelcollection.record_refill` takes a past
   time and level.)
2. **Days or weeks later** (the longer, the better; a nearly empty bottle is
   best): measure the real level and enter it in **Measured oil level**.
   *Spray time since refill* shows the rate you'd get before you commit.
3. Press **Calibrate rate**. The rate and *Oil remaining* both update.

**Measuring a bottle with no markings:**

- Weigh it. Essential oil blends weigh about 0.9 g per mL, so
  mL ≈ (weight − empty bottle weight) ÷ 0.9. Weigh the empty bottle once and
  write the number down.
- Or mark the bottle once: pour in a measured 100 mL at a time and mark each line.

Avoid estimating by eye. A guess in either reading goes straight into the rate.

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

- The diffuser's own *days of oil left* request (cmd `04`) always answers 0, so
  the integration works out days left itself from the same formula. The
  diffuser's own value still shows when it pushes one.
- An unknown status value (cmd `0B`) is read but not used.
- Changing the diffuser's Wi-Fi network from Home Assistant: use the ScentArea app.
- The integration names entities after the device you set up, so several
  diffusers work, but each needs its own card (`device:` prefix).

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

The integration enforces the first two rules, and the HVAC pause handles the last one.
The consumption rate doesn't change how much you smell. It only tells the diffuser
how fast oil is used, so it can estimate what's left. See
[Oil calibration](#oil-calibration-training-the-oil-level).

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
