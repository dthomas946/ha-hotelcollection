"""HVAC pause rules. Pure helpers run anywhere; the simulation needs homeassistant
installed (skipped otherwise)."""

import asyncio
import importlib.util
import pathlib
import sys
import time
from datetime import datetime

import pytest

ROOT = pathlib.Path(__file__).parents[1] / "custom_components" / "hotelcollection"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


gate = _load("gate")
codec = sys.modules.get("codec") or _load("codec")

W = ["Mon", "Tue", "Wed", "Thu", "Fri"]
SLOTS = [
    codec.ScheduleSlot(1, codec.days_to_mask(W), "05:30", "12:00", True, 60, 90),
    codec.ScheduleSlot(5, codec.days_to_mask(["Sat", "Sun"]), "20:00", "23:59", True, 70, 90),
]


def test_fan_running_from_each_kind_of_entity():
    assert gate.fan_running("climate", "heat", {"hvac_action": "idle", "fan_action": "idle"}) is False
    assert gate.fan_running("climate", "heat", {"hvac_action": "heating"}) is True
    assert gate.fan_running("climate", "cool", {"hvac_action": "idle", "fan_action": "on"}) is True
    assert gate.fan_running("climate", "off", {"hvac_action": "fan"}) is True
    assert gate.fan_running("sensor", "0", {}) is False
    assert gate.fan_running("sensor", "1", {}) is True
    assert gate.fan_running("binary_sensor", "on", {}) is True
    assert gate.fan_running("climate", "unavailable", {"hvac_action": "heating"}) is False


def test_scheduled_now():
    assert gate.scheduled_now(SLOTS, datetime(2026, 11, 16, 8, 0)) is True      # Mon, mode 1
    assert gate.scheduled_now(SLOTS, datetime(2026, 11, 16, 12, 0)) is False    # end is exclusive
    assert gate.scheduled_now(SLOTS, datetime(2026, 11, 15, 23, 59)) is True    # 23:59 = end of day
    off = [codec.ScheduleSlot(1, codec.days_to_mask(W), "05:30", "12:00", False, 60, 90)]
    assert gate.scheduled_now(off, datetime(2026, 11, 16, 8, 0)) is False


@pytest.mark.parametrize("scent,fan,sched,fan_for,power,want,status", [
    (False, True, True, 99, True, False, gate.STATUS_OFF_BY_USER),
    (True, True, False, 99, True, False, gate.STATUS_OUTSIDE),
    (True, False, True, 0, True, False, gate.STATUS_WAITING),
    (True, True, True, 5, False, None, gate.STATUS_STARTING),
    (True, True, True, 25, False, True, gate.STATUS_SPRAYING),
    (True, True, True, 5, True, True, gate.STATUS_SPRAYING),   # already on: don't bounce it
])
def test_decide(scent, fan, sched, fan_for, power, want, status):
    assert gate.decide(scent, True, fan, sched, fan_for, 20, power) == (want, status)


# --------------------------------------------------------------- simulation
ha = pytest.importorskip("homeassistant")


class FakeState:
    def __init__(self, entity_id, state, attrs):
        self.entity_id, self.state, self.attributes = entity_id, state, attrs
        self.domain = entity_id.split(".")[0]


class FakeStates:
    def __init__(self):
        self.d = {}

    def get(self, eid):
        return self.d.get(eid)


class FakeHass:
    def __init__(self):
        self.states = FakeStates()
        self.tasks = []

    def async_create_task(self, coro):
        self.tasks.append(asyncio.ensure_future(coro))


class FakeCoordinator:
    def __init__(self, hass):
        self.hass = hass
        self.state = codec.DeviceState(power=True, schedule=list(SLOTS))
        self.gate = None
        self.writes = []

    async def async_write_power_for_gate(self, on):
        self.writes.append(on)
        old = self.state.power
        self.state.power = on
        if old != on:
            self.gate.on_power_changed(on)  # the device's S 08 push comes back


def test_a_morning_with_the_fan_cycling_and_a_manual_override(monkeypatch):
    from homeassistant.util import dt as dt_util
    monkeypatch.setattr(dt_util, "now", lambda: datetime(2026, 11, 16, 8, 0))  # Mon, mode 1 on
    clock = [1000.0]
    monkeypatch.setattr(gate.time, "monotonic", lambda: clock[0])

    async def run():
        hass = FakeHass()
        co = FakeCoordinator(hass)
        g = gate.ScentGate(hass, co, "climate.downstairs_2", 20)
        co.gate = g
        g._schedule_recheck = lambda wait_s: None
        hass.states.d["climate.downstairs_2"] = FakeState("climate.downstairs_2", "heat", {"hvac_action": "idle"})

        await g.evaluate()                       # fan idle -> pause
        assert co.state.power is False and g.status == gate.STATUS_WAITING and g.scent_on

        hass.states.d["climate.downstairs_2"] = FakeState("climate.downstairs_2", "heat", {"hvac_action": "heating"})
        g._fan_on_since = clock[0]
        await g.evaluate()                       # fan just started -> wait for airflow
        assert co.state.power is False and g.status == gate.STATUS_STARTING
        clock[0] += 21
        await g.evaluate()                       # 21 s later -> spray
        assert co.state.power is True and g.status == gate.STATUS_SPRAYING

        # the person turns the Villa off in the ScentArea app (not our write)
        co.state.power = False
        g.on_power_changed(False)
        await asyncio.gather(*hass.tasks)
        assert g.scent_on is False and g.status == gate.STATUS_OFF_BY_USER
        writes_before = list(co.writes)
        clock[0] += 600
        await g.evaluate()                       # fan still running: stays off
        assert co.state.power is False and co.writes == writes_before

        await g.set_scent(True)                  # person turns Scent back on
        assert co.state.power is True and g.status == gate.STATUS_SPRAYING

        hass.states.d["climate.downstairs_2"] = FakeState("climate.downstairs_2", "heat", {"hvac_action": "idle"})
        await g.evaluate()                       # fan stops -> off at once, Scent stays on
        assert co.state.power is False and g.scent_on is True and g.status == gate.STATUS_WAITING

    asyncio.run(run())
