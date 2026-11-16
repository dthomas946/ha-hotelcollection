"""Frame codec for Hotel Collection diffusers that use the ScentArea app (local TCP port 8080).

Pure Python, no Home Assistant imports, so it can be unit-tested or reused
from AppDaemon / Node-RED scripts.

Wire format (reverse-engineered from a Hotel Collection Villa 2.0):

    A5 AA AC | xor | type | cmd | payload... | C5 CC CA

* ``xor``  = XOR of type, cmd and every payload byte.
* ``type`` = ``R`` (0x52) read request / read reply,
             ``W`` (0x57) write request / write ACK (payload ``ACK``),
             ``S`` (0x53) status push after a change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

HEADER = b"\xa5\xaa\xac"
TRAILER = b"\xc5\xcc\xca"

TYPE_READ = 0x52  # 'R'
TYPE_WRITE = 0x57  # 'W'
TYPE_STATUS = 0x53  # 'S'

CMD_NAME = 0x01
CMD_CLOCK = 0x02
CMD_FAN = 0x03
CMD_UNKNOWN_04 = 0x04
CMD_OIL = 0x05
CMD_SCHEDULE = 0x06
CMD_POWER = 0x08
CMD_LOCK = 0x09
CMD_SLOT = 0x0A
CMD_UNKNOWN_0B = 0x0B
CMD_SNAPSHOT = 0x0C

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def checksum(body: bytes) -> int:
    """XOR of all bytes in type + cmd + payload."""
    x = 0
    for b in body:
        x ^= b
    return x


def encode(ftype: int, cmd: int, payload: bytes = b"") -> bytes:
    """Build a complete frame."""
    body = bytes([ftype, cmd]) + payload
    return HEADER + bytes([checksum(body)]) + body + TRAILER


ALL_SLOTS = 0x1F  # cmd 06 takes a slot bitmask: bit0 = slot 1 ... bit4 = slot 5


def read_request(cmd: int, payload: bytes = b"") -> bytes:
    return encode(TYPE_READ, cmd, payload)


def write_request(cmd: int, value: int) -> bytes:
    return encode(TYPE_WRITE, cmd, bytes([value & 0xFF]))


@dataclass
class Frame:
    ftype: int
    cmd: int
    payload: bytes

    @property
    def type_char(self) -> str:
        return chr(self.ftype)

    @property
    def is_ack(self) -> bool:
        return self.ftype == TYPE_WRITE and self.payload == b"ACK"

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Frame({self.type_char} {self.cmd:02X} {self.payload.hex(' ')})"


class FrameParser:
    """Incremental parser for a TCP byte stream."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[Frame]:
        self._buf.extend(data)
        frames: list[Frame] = []
        while True:
            start = self._buf.find(HEADER)
            if start < 0:
                # keep a possible partial header at the end
                del self._buf[: max(0, len(self._buf) - 2)]
                return frames
            if start:
                del self._buf[:start]
            search_from = len(HEADER) + 3  # xor + type + cmd minimum
            found = False
            while True:
                end = self._buf.find(TRAILER, search_from)
                if end < 0:
                    return frames  # wait for more data
                xor = self._buf[3]
                body = bytes(self._buf[4:end])
                if len(body) >= 2 and checksum(body) == xor:
                    frames.append(Frame(body[0], body[1], body[2:]))
                    del self._buf[: end + len(TRAILER)]
                    found = True
                    break
                # trailer bytes may occur inside payload; try the next one
                search_from = end + 1
                if search_from > 512:
                    break
            if not found:
                # unrecoverable garbage: drop this header and resync
                del self._buf[: len(HEADER)]


# ---------------------------------------------------------------- decoders


@dataclass
class OilInfo:
    capacity_ml: int
    remaining_ml: int
    rate_ml_h: float

    @property
    def percent(self) -> float:
        return round(100 * self.remaining_ml / self.capacity_ml, 1) if self.capacity_ml else 0.0


def decode_oil(payload: bytes) -> OilInfo | None:
    """cmd 05: capacity16, remaining16, rate (tenths of mL/h)."""
    if len(payload) < 5:
        return None
    return OilInfo(
        capacity_ml=int.from_bytes(payload[0:2], "big"),
        remaining_ml=int.from_bytes(payload[2:4], "big"),
        rate_ml_h=payload[4] / 10,
    )


def decode_clock(payload: bytes) -> datetime | None:
    """cmd 02: year16, month, day, hour, minute, second, weekday."""
    if len(payload) < 7:
        return None
    try:
        return datetime(
            int.from_bytes(payload[0:2], "big"),
            payload[2],
            payload[3],
            payload[4],
            payload[5],
            payload[6],
        )
    except ValueError:
        return None


def decode_name(payload: bytes) -> str:
    """cmd 01: one index byte, then a zero-padded ASCII name."""
    raw = payload[1:] if payload else b""
    return raw.split(b"\x00", 1)[0].decode("ascii", "replace")


@dataclass
class ScheduleSlot:
    slot: int
    days_mask: int
    start: str
    end: str
    enabled: bool
    work_s: int
    pause_s: int

    @property
    def days(self) -> list[str]:
        return [d for i, d in enumerate(DAY_NAMES) if self.days_mask & (1 << i)]

    def as_dict(self) -> dict:
        return {
            "slot": self.slot,
            "days": self.days,
            "start": self.start,
            "end": self.end,
            "enabled": self.enabled,
            "work_s": self.work_s,
            "pause_s": self.pause_s,
        }


def _slot_from(b: bytes, has_enabled: bool) -> ScheduleSlot:
    if has_enabled:
        enabled = bool(b[6])
        work = int.from_bytes(b[7:9], "big")
        pause = int.from_bytes(b[9:11], "big")
    else:
        enabled = b[1] != 0
        work = int.from_bytes(b[6:8], "big")
        pause = int.from_bytes(b[8:10], "big")
    return ScheduleSlot(
        slot=b[0],
        days_mask=b[1],
        start=f"{b[2]:02d}:{b[3]:02d}",
        end=f"{b[4]:02d}:{b[5]:02d}",
        enabled=enabled,
        work_s=work,
        pause_s=pause,
    )


def decode_schedule(payload: bytes) -> list[ScheduleSlot]:
    """cmd 06: n x 11-byte slots, for the slots selected by the request's bitmask."""
    return [_slot_from(payload[i : i + 11], True) for i in range(0, len(payload) - 10, 11)]


def decode_slot(payload: bytes) -> ScheduleSlot | None:
    """cmd 0A: one 10-byte slot (no enabled byte; days==0 means off)."""
    if len(payload) < 10:
        return None
    return _slot_from(payload, False)


@dataclass
class DeviceState:
    name: str | None = None
    power: bool | None = None
    fan: bool | None = None
    lock: bool | None = None
    oil: OilInfo | None = None
    clock: datetime | None = None
    schedule: list[ScheduleSlot] = field(default_factory=list)
    raw: dict[int, bytes] = field(default_factory=dict)

    def apply(self, frame: Frame) -> bool:
        """Update state from a frame. Returns True if anything changed."""
        if frame.is_ack:
            return False
        if frame.ftype not in (TYPE_READ, TYPE_STATUS):
            return False
        p = frame.payload
        before = (self.name, self.power, self.fan, self.lock, self.oil, self.schedule)
        self.raw[frame.cmd] = p
        if frame.cmd == CMD_NAME:
            self.name = decode_name(p)
        elif frame.cmd == CMD_CLOCK:
            self.clock = decode_clock(p)
            return False  # clock ticks are not interesting state changes
        elif frame.cmd == CMD_POWER and p:
            self.power = bool(p[0])
        elif frame.cmd == CMD_FAN and p:
            self.fan = bool(p[0])
        elif frame.cmd == CMD_LOCK and p:
            self.lock = bool(p[0])
        elif frame.cmd == CMD_OIL:
            self.oil = decode_oil(p) or self.oil
        elif frame.cmd == CMD_SCHEDULE:
            self.schedule = decode_schedule(p)
        after = (self.name, self.power, self.fan, self.lock, self.oil, self.schedule)
        return before != after
