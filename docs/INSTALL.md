# Installing and setting up Hotel Collection

This guide takes a Hotel Collection diffuser (Villa 2.0, or another model that
uses the ScentArea app) from unboxed to fully controlled by Home Assistant. Every
setting you may need to change is listed in [Your settings](#3-your-settings),
together with where to change it. Nothing needs a code edit.

Want an AI assistant to do the setup for you? Hand it
[AI_SETUP.md](AI_SETUP.md).

---

## 1. Before you start

- **Home Assistant 2025.2 or newer**, with [HACS](https://hacs.xyz) installed.
- **Connect the diffuser to your Wi-Fi** once with the ScentArea app (Wi-Fi mode).
  After that the app is optional. AP mode (your phone joins the diffuser's own
  hotspot) still works alongside Home Assistant.
- **Give the diffuser a fixed IP address** with a DHCP reservation in your router.
  The integration connects by IP address.
- Home Assistant must be able to reach the diffuser on **TCP port 8080**. If your
  IoT devices are on a separate VLAN, allow Home Assistant → diffuser:8080.
- **Don't port-scan the diffuser with version detection** (`nmap -sV`). It
  accepts the scanner's junk as commands and changes settings. See the README.

## 2. Install

1. In HACS, open **⋮ → Custom repositories** and add
   `https://github.com/dthomas946/ha-hotelcollection`, type **Integration**.
2. Search HACS for **Hotel Collection**, download it, and **restart Home Assistant**.
3. Go to **Settings → Devices & services → Add integration → Hotel Collection** and fill in:

   | Field | What to enter |
   |---|---|
   | Host | The diffuser's IP address |
   | Port | `8080` (leave as is) |
   | Name | What you call the diffuser, e.g. `Villa`. This name becomes the start of every entity ID: `Villa` gives `switch.villa_power`, `sensor.villa_oil_remaining`, and so on. |

Updates arrive through HACS like any other integration. Restart Home Assistant
after each update.

## 3. Your settings

Every setting lives in one of two places:

- **The device page:** Settings → Devices & services → Hotel Collection → your
  device. Look under *Controls* and *Configuration*.
- **Configure:** the **Configure** button on the integration's entry.

In the table, `<name>` stands for the name you gave the diffuser, in lower case
(`villa`).

| Setting | Where | Entity | Set it to |
|---|---|---|---|
| **Bottle size** | Device page → Configuration | `number.<name>_bottle_size_setting` | Your oil bottle's capacity in mL (the Villa 2.0 bottle is 800 mL) |
| **Oil to add** | Device page → Configuration | `number.<name>_oil_to_add` | How much oil you pour in per refill (e.g. 500 mL). The **Add oil** button adds this. |
| **Consumption rate** | Device page → Controls | `number.<name>_consumption_rate_setting` | mL per hour of spraying. Start with the app's value; [calibrate](#5-oil-level-and-calibration) it later. |
| **Correct oil level** | Device page → Controls | `number.<name>_oil_remaining_setting` | What's actually in the bottle, whenever you know |
| **HVAC fan source** | Configure, or device page → Configuration | `select.<name>_hvac_fan_source` | The entity that shows your HVAC blower is running. See [HVAC pause](#4-hvac-pause-diffusers-that-feed-a-duct). `none` turns the pause off. |
| **HVAC start delay** | Configure, or device page → Configuration | `number.<name>_hvac_start_delay` | Seconds of airflow before spraying starts (default 20) |
| **Fan** | Device page → Controls | `switch.<name>_fan` | **Off** if the diffuser feeds an HVAC duct, **on** if it stands in the room it scents |
| **Child lock** | Device page → Configuration | `switch.<name>_child_lock` | As you like |
| **Scent name** | Device page → Controls | `text.<name>_scent` | The oil you're using. Shown on the card; the diffuser doesn't store it. |
| **Schedule** (5 modes) | The dashboard card's pencil icons, or the `hotelcollection.set_mode` action | — | Days, start/end, spray and pause seconds |

The device enforces a few fixed limits, so they are not settings:

- Spray and pause times are 5–300 s; 15 s or more is recommended.
- A schedule mode can't run past midnight. Split it at 23:59 / 00:00.
- The bottle's maximum fill is 90 %, and the low-oil warning comes at 10 %. Both
  come from the manual.
- Calibration needs at least 5 hours of spraying.

## 4. HVAC pause (diffusers that feed a duct)

A duct-fed diffuser should spray only while the HVAC blower moves air. Otherwise
the mist settles in the ductwork. With an **HVAC fan source** set, the diffuser
runs only when all of the following are true:

> **Scent** is on **and** the blower is running **and** a schedule mode is active.

It stops as soon as the blower stops. If you turn the diffuser off yourself (on
the card, in the app, or with the button on the unit), it stays off until you
turn **Scent** back on. The pause never overrides you.

The integration recognises these as a running blower:

| Fan source entity | Counts as "running" when |
|---|---|
| `climate.*` (a thermostat) | `hvac_action` is heating / cooling / fan / drying, or `fan_action` is on |
| `binary_sensor.*`, `switch.*`, `input_boolean.*`, `fan.*` | the state is `on` |
| `sensor.*` | the value is above 0 (e.g. blower power or a 0/1 sensor) |

Choose the most direct signal you have: a blower relay or blower power sensor
first, then the thermostat. If several systems share the duct, make a template
binary sensor that is `on` when any of them blows, and pick that.

Check it: **Scent status** (`sensor.<name>_scent_status`) should read
*Paused: HVAC fan off* while the blower is idle and *Spraying* while it runs.

## 5. Oil level and calibration

The diffuser has **no oil sensor**. Oil remaining, days left and the low-oil
warning are all *last level entered − consumption rate × hours of spraying*, so
they are only as good as the rate. You train the rate over **two or three refills
(a few months)**. Each refill-to-measurement period is one session:

1. **At the refill:** set **Oil to add** to what you poured in and press
   **Add oil**. That also restarts the *Spray time since refill* count.
2. **Days or weeks later** (the longer, the better): measure the real level and
   enter it in **Measured oil level**. Weigh the bottle (about 0.9 g per mL, minus
   the empty bottle's weight), or mark it once with measured pours; don't guess
   by eye. *Spray time since refill* shows the rate this reading would give.
3. Press **Calibrate rate**. The rate becomes *(level at refill − measured) ÷
   spraying hours*, and the oil level becomes your reading.

The first session gives a rough rate; later sessions with larger drops refine it.
Re-train whenever you change the oil or the spray/pause times. Past sessions are
kept in the `calibration_history` attribute of *Spray time since refill*. The
[README](../README.md#oil-calibration-training-the-oil-level) explains the method
in full.

## 6. Dashboard

The integration includes a card. You don't need to add a resource:

```yaml
type: custom:hotelcollection-card
device: villa        # your <name>
name: Villa          # optional title
```

The card shows a weekly schedule timeline, mode on/off switches with an editor,
power, the HVAC-pause status, and the oil level with mL / fl oz, the 90 % max-fill
mark and days left.

### A complete page

Paste this as a new view in a dashboard (**Edit → ⋮ → Raw configuration editor**,
under `views:`). Replace `villa` with your `<name>` and `800` with your bottle size.

```yaml
- title: Diffuser
  path: diffuser
  icon: mdi:scent
  type: sections
  max_columns: 4
  sections:
    - type: grid
      column_span: 2
      cards:
        - type: custom:hotelcollection-card
          device: villa
          grid_options: {columns: full}
    - type: grid
      cards:
        - {type: heading, heading: Details, icon: mdi:scent}
        - {type: tile, entity: text.villa_scent, name: Scent}
        - {type: tile, entity: sensor.villa_scent_status, name: Status}
        - type: tile
          entity: number.villa_consumption_rate_setting
          name: Consumption rate
          features: [{type: numeric-input, style: buttons}]
        - {type: tile, entity: sensor.villa_oil_days_left, name: Oil days left, grid_options: {columns: 6}}
        - {type: tile, entity: number.villa_oil_remaining_setting, name: Correct oil level, grid_options: {columns: 6}}
        - type: tile
          entity: button.villa_oil_refilled
          name: Add oil
          tap_action:
            action: perform-action
            perform_action: button.press
            target: {entity_id: button.villa_oil_refilled}
            confirmation: {text: Add the Oil to add amount to the oil level?}
    - type: grid
      cards:
        - {type: heading, heading: Oil level, icon: mdi:bottle-tonic-outline}
        - type: gauge
          entity: sensor.villa_oil_remaining
          name: Oil remaining
          unit: mL
          min: 0
          max: 800                     # bottle size
          needle: true
          segments:                    # 10 % / 20 % / 90 % of the bottle
            - {from: 0, color: '#db4437'}
            - {from: 80, color: '#ffa600'}
            - {from: 160, color: '#43a047'}
            - {from: 720, color: '#7e57c2'}
    - type: grid
      cards:
        - {type: heading, heading: Calibration, icon: mdi:tune-variant}
        - {type: tile, entity: sensor.villa_spray_time_since_refill, name: Spray time since refill, grid_options: {columns: 6}}
        - {type: tile, entity: number.villa_oil_to_add, name: Oil to add, grid_options: {columns: 6}}
        - {type: tile, entity: number.villa_level_at_last_refill, name: Level at last refill, grid_options: {columns: 6}}
        - {type: tile, entity: number.villa_measured_oil_level, name: Measured oil level, grid_options: {columns: 6}}
        - type: tile
          entity: button.villa_calibrate_rate
          name: Calibrate rate
          tap_action:
            action: perform-action
            perform_action: button.press
            target: {entity_id: button.villa_calibrate_rate}
            confirmation: {text: Set the rate and oil level from the measured level?}
```

## 7. Troubleshooting

| Symptom | Try |
|---|---|
| "Cannot connect" when adding | Check the IP, that port 8080 is reachable from Home Assistant, and that the diffuser is on Wi-Fi (its light). Power-cycle the diffuser. |
| Entities go *unavailable* now and then | The diffuser sometimes refuses new connections for a while. Home Assistant reconnects on its own; a power cycle clears it at once. |
| Card says *Custom element doesn't exist* | Refresh the browser (on the phone app: Settings → Companion app → Reset frontend cache). |
| HACS shows a commit like `708ea76` instead of `v0.7.0` | Redownload from HACS and pick the latest release. Files copied in by hand aren't tracked by HACS. |
| Pump never runs with the HVAC pause on | Check *Scent status*. *Paused: HVAC fan off* while air is moving means the fan source isn't seen as running; pick a more direct signal (section 4). |
| Oil level drifts from reality | Calibrate (section 5). |
