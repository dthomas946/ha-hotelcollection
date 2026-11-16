# Hotel Collection local protocol (TCP 8080)

Reverse-engineered November 2026 from a Hotel Collection Villa 2.0 by listening
to the port while using the ScentArea app. Plain TCP, no encryption, no login.
Several clients can be connected at once; every client receives status pushes.

The cloud link (MQTT to `public.iot-as-mqtt.ap-southeast-1.aliyuncs.com:1883`,
Alibaba IoT) is TLS-encrypted and is not used by this integration.

## Frame

```
A5 AA AC | xor | type | cmd | payload … | C5 CC CA
```

- `xor` — XOR of `type`, `cmd` and every payload byte.
- `type` — `R` 0x52 read (request and reply), `W` 0x57 write (request; the
  reply carries payload `ACK`), `S` 0x53 status push sent after any change.

Read request: `A5 AA AC <0x52^cmd> 52 <cmd> C5 CC CA`
Write request: `A5 AA AC <xor> 57 <cmd> <value> C5 CC CA` → reply `W <cmd> ACK`, then `S <cmd> <value>`.

On connect the device sends `R 02` (its clock).

## Commands

| cmd | Read reply payload | Meaning | Writable |
|---|---|---|---|
| 01 | `01` + 16-byte zero-padded ASCII | Device name (`Device_01`) | ? |
| 02 | year16, month, day, hour, min, sec, weekday (1 = Mon … 7 = Sun) | Device clock | ? |
| 03 | `00`/`01` | Fan | ✔ |
| 04 | 16-bit | Unknown | |
| 05 | capacity16, remaining16, rate8 | Bottle mL, remaining mL, rate in 0.1 mL/h | ? |
| 06 | n × 11-byte slots | Schedule — request takes a 1-byte slot bitmask (`1F` = all 5); with no mask the reply is an arbitrary subset | ? |
| 08 | `00`/`01` | Power | ✔ |
| 09 | `00`/`01` | Child lock | ✔ |
| 0A | 10-byte slot | Always slot 5 in a 10-byte form; purpose unclear | ? |
| 0B | 4 bytes | Unknown | |
| 0C | clock + misc + oil + slot + flags | Status snapshot | |
| 0D–1F | — | No reply | |

All integers are big-endian.

### Schedule slot (cmd 06, 11 bytes)

`slot · days · startH · startM · endH · endM · enabled · work16 · pause16`

`days` bit 0 = Monday … bit 6 = Sunday (0x1F = Mon–Fri, 0x60 = Sat–Sun).
`work`/`pause` are seconds.

cmd 0A uses the same layout without the `enabled` byte (10 bytes); `days = 0`
means the slot is off.

## Example frames

```
R 05  a5 aa ac 69 52 05 01 f4 01 e1 2b c5 cc ca     500 mL, 481 mL left, 4.3 mL/h
W 08  a5 aa ac 5f 57 08 00 c5 cc ca                 power off
ACK   a5 aa ac 16 57 08 41 43 4b c5 cc ca           W 08 "ACK"
S 08  a5 aa ac 5b 53 08 00 c5 cc ca                 power is now off
```
