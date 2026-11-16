"""Codec tests built from real frames captured from a Hotel Collection Villa 2.0
on 2026-11-15. Run with: python -m pytest tests/"""

import importlib.util
import pathlib
import sys

_spec = importlib.util.spec_from_file_location(
    "codec",
    pathlib.Path(__file__).parents[1] / "custom_components" / "hotelcollection" / "codec.py",
)
codec = importlib.util.module_from_spec(_spec)
sys.modules["codec"] = codec
_spec.loader.exec_module(codec)

H = bytes.fromhex

R01 = H("a5aaac34520101" "4465766963655f3031" "00000000000000" "c5ccca")
R02 = H("a5aaac97" "5202" "07ea0b0f14172a07" "c5ccca")
R05 = H("a5aaac69" "5205" "01f401e12b" "c5ccca")
R06_TWO = H("a5aaac3a5206" "011f051e0c0001003c005a" "036009000d0001003c005a" "c5ccca")
R06_FIVE = H(
    "a5aaac06" "5206"
    "011f051e0c0001003c005a"
    "021f0d1e100001003c005a"
    "036009000d0001003c005a"
    "041f150016000100" "46005a"
    "056014001" "73b01" "0046005a"
    "c5ccca"
)
R0A = H("a5aaac79" "520a" "05001400173b0046005a" "c5ccca")
W08_ACK = H("a5aaac16" "5708" "41434b" "c5ccca")
S08_OFF = H("a5aaac5b" "5308" "00" "c5ccca")
S08_ON = H("a5aaac5a" "5308" "01" "c5ccca")
S03_ON = H("a5aaac51" "5303" "01" "c5ccca")
S09_ON = H("a5aaac5b" "5309" "01" "c5ccca")


def parse(data: bytes):
    return codec.FrameParser().feed(data)


def test_requests_match_what_worked_on_the_device():
    assert codec.write_request(codec.CMD_POWER, 0) == H("a5aaac5f570800c5ccca")
    assert codec.write_request(codec.CMD_POWER, 1) == H("a5aaac5e570801c5ccca")
    assert codec.read_request(0x01) == H("a5aaac535201c5ccca")
    assert codec.read_request(0x06) == H("a5aaac545206c5ccca")


def test_every_captured_frame_parses_with_valid_checksum():
    for raw in (R01, R02, R05, R06_TWO, R06_FIVE, R0A, W08_ACK, S08_OFF, S08_ON, S03_ON, S09_ON):
        frames = parse(raw)
        assert len(frames) == 1, raw.hex()


def test_stream_split_across_reads():
    p = codec.FrameParser()
    blob = R02 + W08_ACK + S08_OFF + R05
    out = []
    for i in range(0, len(blob), 5):
        out += p.feed(blob[i : i + 5])
    assert [(f.type_char, f.cmd) for f in out] == [("R", 2), ("W", 8), ("S", 8), ("R", 5)]


def test_garbage_between_frames_is_skipped():
    frames = parse(b"\x00\x13junk" + S08_ON + b"\xff\xff" + R05)
    assert [f.cmd for f in frames] == [8, 5]


def test_name_clock_oil():
    assert codec.decode_name(parse(R01)[0].payload) == "Device_01"
    clk = codec.decode_clock(parse(R02)[0].payload)
    assert (clk.year, clk.month, clk.day, clk.hour, clk.minute, clk.second) == (2026, 11, 15, 20, 23, 42)
    oil = codec.decode_oil(parse(R05)[0].payload)
    assert (oil.capacity_ml, oil.remaining_ml, oil.rate_ml_h) == (500, 481, 4.3)
    assert oil.percent == 96.2


def test_schedule_two_and_five_slots():
    two = codec.decode_schedule(parse(R06_TWO)[0].payload)
    assert [s.slot for s in two] == [1, 3]
    assert two[0].days == ["Mon", "Tue", "Wed", "Thu", "Fri"]
    assert (two[0].start, two[0].end, two[0].work_s, two[0].pause_s) == ("05:30", "12:00", 60, 90)
    assert two[1].days == ["Sat", "Sun"]
    five = codec.decode_schedule(parse(R06_FIVE)[0].payload)
    assert [s.slot for s in five] == [1, 2, 3, 4, 5]
    assert (five[4].start, five[4].end, five[4].work_s) == ("20:00", "23:59", 70)


def test_single_slot_cmd_0a():
    s = codec.decode_slot(parse(R0A)[0].payload)
    assert (s.slot, s.days, s.start, s.end, s.enabled, s.work_s, s.pause_s) == (
        5, [], "20:00", "23:59", False, 70, 90)


def test_state_machine():
    st = codec.DeviceState()
    for raw in (R01, S08_ON, S03_ON, S09_ON, R05, R06_TWO):
        st.apply(parse(raw)[0])
    assert (st.name, st.power, st.fan, st.lock) == ("Device_01", True, True, True)
    assert st.oil.remaining_ml == 481
    assert len(st.schedule) == 2
    assert st.apply(parse(S08_OFF)[0]) is True and st.power is False
    assert st.apply(parse(W08_ACK)[0]) is False


def test_schedule_request_uses_slot_mask():
    # verified 2026-11-15: R 06 1F returns all five slots
    assert codec.read_request(codec.CMD_SCHEDULE, bytes([codec.ALL_SLOTS])) == H("a5aaac4b52061fc5ccca")
