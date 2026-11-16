# ScentArea Local

Local, cloud-free Home Assistant control of **ScentArea** Wi-Fi scent diffusers
(sold as Hotel Collection Villa 2.0, Aroma360 Mini360 / VanGogh360 2.0 and other
white-label units that pair with the *ScentArea* app).

The diffuser keeps a plain TCP control port open on your network (**8080**).
This integration talks to that port directly — no Alibaba cloud, no account,
and the ScentArea app keeps working alongside it.

Verified on: Hotel Collection Villa 2.0 (Bouffalo Lab Wi-Fi module), November 2026.

## What you get

| Entity | Type | Notes |
|---|---|---|
| Power | switch | Instant; changes made in the app show up immediately |
| Fan | switch | |
| Child lock | switch (config) | |
| Oil remaining | sensor, mL | From the device |
| Oil level | sensor, % | Remaining ÷ bottle size |
| Bottle size | sensor, mL (diagnostic) | |
| Consumption rate | sensor, mL/h | The rate set in the app |
| Run time remaining | sensor, h | Remaining ÷ rate — hours of *spraying* time, not calendar time |
| Active schedule slots | sensor | Full slot list (days, times, work/pause) in attributes |
| Device clock | sensor (diagnostic, off by default) | |
| Scent | text | Kept in HA — the diffuser does not store the scent name |

## Install

1. Give the diffuser a fixed IP (DHCP reservation) in your router.
2. HACS → ⋮ → **Custom repositories** → add `https://github.com/dthomas946/ha-scentarea-local`, category **Integration**.
3. Download **ScentArea Local**, restart Home Assistant.
4. Settings → Devices & services → **Add integration** → *ScentArea Local* → enter the IP.

If you use firewall groups/VLANs, allow Home Assistant → diffuser on TCP 8080.

## Not yet supported

- Editing the schedule (read-only for now; edit it in the app).
- Changing the consumption rate or bottle size.
- Unknown values: cmd `04`, cmd `0B`.

## ⚠️ Don't port-scan with version detection

`nmap -sV` against port 8080 sends junk that the diffuser accepts as commands —
it flipped settings and cleared schedule slots during development. Plain port
scans are fine.

## Protocol

See [docs/protocol.md](docs/protocol.md). The codec is pure Python
(`custom_components/scentarea_local/codec.py`) and tested against real captures
(`tests/test_codec.py`).

Not affiliated with ScentArea, Hotel Collection or Aroma360.
