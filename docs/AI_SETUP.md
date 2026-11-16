# AI setup guide: Hotel Collection diffuser in Home Assistant

**For the person:** give this file to an AI assistant that can work with your
Home Assistant, for example Claude with a Home Assistant MCP server, or Home
Assistant's own Assist with an AI conversation agent. Then ask it: *"Set up my
Hotel Collection diffuser using this guide."* It will ask you a few questions and
make the settings for you.

**For the AI:** the rest of this file is written to you. Follow it in order. Ask
the person whenever a step says **ASK**; don't guess those answers.

---

## What you are working with

- Integration domain `hotelcollection`. It controls the diffuser locally over
  TCP 8080, with no cloud.
- Entity IDs start with the name given at setup, lower-cased. Below, `<p>` is
  that prefix (e.g. `villa` → `switch.villa_power`). Find it by listing entities
  of the `hotelcollection` integration, or search entity IDs for
  `_scent_status`.
- All settings are entities or actions. **Never edit files under `.storage` or
  the integration's code.**

| Entity / action | Purpose |
|---|---|
| `switch.<p>_scent` | The person's on/off. Respect it; never turn it on unless asked. |
| `switch.<p>_power` | The pump. With the HVAC pause on, the integration drives it; don't automate it yourself. |
| `switch.<p>_fan` | The diffuser's built-in blower |
| `sensor.<p>_scent_status` | `spraying`, `starting`, `waiting_for_hvac`, `outside_schedule`, `off_by_user`, `off` |
| `select.<p>_hvac_fan_source` | Entity that shows the HVAC blower is running; `none` = HVAC pause off |
| `number.<p>_hvac_start_delay` | Seconds of airflow before spraying (0–300, default 20) |
| `number.<p>_bottle_size_setting` | Bottle capacity, mL |
| `number.<p>_oil_to_add` | mL poured in per refill (what **Add oil** adds) |
| `number.<p>_consumption_rate_setting` | mL per hour of spraying (0.1–25.5) |
| `number.<p>_oil_remaining_setting` | Oil level the diffuser counts down from |
| `button.<p>_oil_refilled` ("Add oil") | Level += Oil to add (capped at the bottle size); restarts the calibration count |
| `number.<p>_level_at_last_refill`, `number.<p>_measured_oil_level`, `button.<p>_calibrate_rate` | Calibration |
| `hotelcollection.set_mode` | Edit a schedule mode: `mode` 1–5 plus any of `enabled`, `days` [Mon..Sun], `start`, `end`, `spray_seconds`, `pause_seconds` (5–300) |
| `hotelcollection.record_refill` | Log a past refill: `level_ml`, `refilled_at`, optional `run_hours` |

## Step 1: Check the integration

Confirm `sensor.<p>_scent_status` exists and `switch.<p>_power` isn't
`unavailable`. If the integration is missing, the person has to install it first
([INSTALL.md](INSTALL.md), sections 2–3). Adding the integration needs the
diffuser's IP address, so **ASK** for it if you are the one adding it.

## Step 2: Is the diffuser connected to the HVAC?

**ASK:** "Is the diffuser connected to your HVAC ductwork, or does it stand in
the room it scents?"

- **In the room:** set `switch.<p>_fan` **on**, set `select.<p>_hvac_fan_source`
  to `none`, and skip to step 4.
- **Connected to the ducts:** set `switch.<p>_fan` **off**. Its built-in blower
  only pushes mist into the room the unit sits in (an attic, a closet). Then do
  step 3.

## Step 3: Choose the HVAC fan source

Find the best signal that **the blower serving the diffuser's duct is moving
air**. Prefer the first that exists:

1. A blower relay or "G/fan call" `binary_sensor` / `switch` (`on` = blowing).
2. A blower power or current `sensor` (> 0 = blowing).
3. The `climate.*` thermostat for that system. It counts as running when
   `hvac_action` is heating/cooling/fan/drying or `fan_action` is on.

How to look: list the entities in the options of `select.<p>_hvac_fan_source`.
The integration pre-filters to climate and fan entities and anything named
fan, blower or furnace. Check each candidate's current state and attributes.
With more than one HVAC system, **ASK** which system's ducts the diffuser feeds.
If the answer is "either", offer to create a template binary sensor that is `on`
when any of the relevant blowers runs, and use that.

**ASK** the person to confirm your choice, then:

```yaml
action: select.select_option
target: {entity_id: select.<p>_hvac_fan_source}
data: {option: <chosen entity_id>}
```

The integration reloads for a few seconds. Verify: with the blower idle,
`sensor.<p>_scent_status` = `waiting_for_hvac` (or `outside_schedule` if no mode
is active right now). Leave `number.<p>_hvac_start_delay` at 20 s unless the
person asks otherwise.

## Step 4: Oil settings

**ASK:** bottle size (the Villa 2.0's is 800 mL) and how much oil they pour in per
refill. Set:

```yaml
action: number.set_value
target: {entity_id: number.<p>_bottle_size_setting}
data: {value: 800}
---
action: number.set_value
target: {entity_id: number.<p>_oil_to_add}
data: {value: 500}
```

Don't change the consumption rate without a measured level (step 6).

## Step 5: Dashboard (optional)

**ASK** whether they want a diffuser page on a dashboard, and which dashboard.
Use the view in [INSTALL.md, section 6](INSTALL.md#a-complete-page). Replace
`villa` with `<p>`, and set the gauge `max` and segments to 0 / 10 % / 20 % /
90 % of the bottle size. Add the view through the dashboard API. Don't
overwrite the dashboard's other views.

## Step 6: Calibration (later, not during setup)

Only when the person gives you a **real reading** of the bottle (by weight: oil
≈ 0.9 g/mL):

1. Make sure `number.<p>_level_at_last_refill` holds the level right after the
   last refill. If they refilled earlier without logging it, use
   `hotelcollection.record_refill` with `level_ml` and `refilled_at`.
2. Set `number.<p>_measured_oil_level` to the reading.
3. Show them the `calibrated_rate_preview` attribute of
   `sensor.<p>_spray_time_since_refill`, and press `button.<p>_calibrate_rate`
   only if they agree.

## Rules

- The person stays in control: never turn `switch.<p>_scent` on, and never
  automate `switch.<p>_power` yourself.
- Don't scan the diffuser's ports, and especially not with `nmap -sV`; it takes
  the probes as commands.
- Don't run other software against port 8080 while the integration is
  connected. The diffuser handles only a few connections.
- Summarise what you changed at the end, with the entity IDs.

## For Home Assistant Assist (voice)

Assist can change these settings by voice once the entities are exposed:
**Settings → Voice assistants → Expose**, then add `select.<p>_hvac_fan_source`,
`number.<p>_hvac_start_delay`, `number.<p>_oil_to_add`,
`number.<p>_measured_oil_level`, `switch.<p>_scent`, and the buttons. After that,
"turn off the scent" or "set the diffuser's HVAC start delay to 30 seconds" work
directly.
