"""HVAC pause: run the diffuser only while the HVAC fan moves air.

Rules (re-checked on every fan change, schedule change and every 30 s):

    Villa power = Scent switch ON  AND  HVAC fan running  AND  a mode scheduled now

* The Scent switch is the person's intent. Turning the Villa off anywhere else
  (dashboard power switch, ScentArea app, the button on the unit) turns Scent off,
  and the gate leaves it off until the person turns it back on.
* Power comes on a few seconds after the fan starts (air must be moving first) and
  goes off as soon as the fan stops, so mist does not settle in the ducts.

Pure helpers at the top are unit-tested without Home Assistant.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

_LOGGER = logging.getLogger(__name__)

RUNNING_ACTIONS = {"heating", "cooling", "fan", "drying", "preheating", "defrosting"}
ON_WORDS = {"on", "running", "true", "fan", "active", "1"}

STATUS_SPRAYING = "spraying"
STATUS_STARTING = "starting"
STATUS_WAITING = "waiting_for_hvac"
STATUS_OUTSIDE = "outside_schedule"
STATUS_OFF_BY_USER = "off_by_user"
STATUS_OFF = "off"
STATUSES = [STATUS_SPRAYING, STATUS_STARTING, STATUS_WAITING, STATUS_OUTSIDE, STATUS_OFF_BY_USER, STATUS_OFF]

OWN_WRITE_WINDOW_S = 15


def fan_running(domain: str, state: str | None, attributes: dict | None) -> bool:
    """Is the HVAC fan moving air, judged from one entity's state."""
    if state in (None, "unknown", "unavailable"):
        return False
    attrs = attributes or {}
    if domain == "climate":
        if str(attrs.get("hvac_action", "")).lower() in RUNNING_ACTIONS:
            return True
        return str(attrs.get("fan_action", "")).lower() in ON_WORDS
    if domain == "sensor":
        try:
            return float(state) > 0
        except (TypeError, ValueError):
            return str(state).lower() in ON_WORDS
    return str(state).lower() == "on"


def scheduled_now(slots, now: datetime) -> bool:
    """Does an enabled schedule mode cover `now`? (modes never cross midnight)"""
    day = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[now.weekday()]
    minute = now.hour * 60 + now.minute
    for s in slots:
        if not s.enabled or day not in s.days:
            continue
        sh, sm = (int(x) for x in s.start.split(":"))
        eh, em = (int(x) for x in s.end.split(":"))
        end = 24 * 60 if (eh, em) == (23, 59) else eh * 60 + em
        if sh * 60 + sm <= minute < end:
            return True
    return False


def spray_fraction_now(slots, now: datetime) -> float:
    """Share of the time the pump sprays right now: spray / (spray + pause) of the
    running mode, 0 outside every enabled mode."""
    day = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[now.weekday()]
    minute = now.hour * 60 + now.minute
    for s in slots:
        if not s.enabled or day not in s.days or s.work_s + s.pause_s == 0:
            continue
        sh, sm = (int(x) for x in s.start.split(":"))
        eh, em = (int(x) for x in s.end.split(":"))
        end = 24 * 60 if (eh, em) == (23, 59) else eh * 60 + em
        if sh * 60 + sm <= minute < end:
            return s.work_s / (s.work_s + s.pause_s)
    return 0.0


def decide(scent_on: bool, gate_active: bool, fan_on: bool, scheduled: bool,
           fan_on_for_s: float, start_delay_s: float, power_on: bool | None) -> tuple[bool | None, str]:
    """Return (desired power or None for 'leave as is', status)."""
    if not scent_on:
        return False, STATUS_OFF_BY_USER
    if not gate_active:
        return True, STATUS_SPRAYING if power_on else STATUS_OFF
    if not scheduled:
        return False, STATUS_OUTSIDE
    if not fan_on:
        return False, STATUS_WAITING
    if not power_on and fan_on_for_s < start_delay_s:
        return None, STATUS_STARTING
    return True, STATUS_SPRAYING


class ScentGate:
    """Home Assistant side of the rules above. One per diffuser."""

    def __init__(self, hass, coordinator, fan_entity: str | None, start_delay_s: float) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.fan_entity = fan_entity or None
        self.start_delay_s = start_delay_s
        self.scent_on = True
        self.status = STATUS_OFF
        self._fan_on_since: float | None = None
        self._pending: tuple[bool, float] | None = None  # our own power write in flight
        self._unsubs = []
        self._busy = False
        self._listeners = []

    # ---------------------------------------------------------------- wiring
    @property
    def active(self) -> bool:
        return self.fan_entity is not None

    def start(self) -> None:
        from homeassistant.helpers.event import (
            async_track_state_change_event,
            async_track_time_interval,
        )

        if self.fan_entity:
            st = self.hass.states.get(self.fan_entity)
            if st and self._fan_state(st):
                self._fan_on_since = time.monotonic() - 3600  # already running at start
            self._unsubs.append(
                async_track_state_change_event(self.hass, [self.fan_entity], self._on_fan_event)
            )
        self._unsubs.append(
            async_track_time_interval(self.hass, self._on_tick, timedelta(seconds=30))
        )
        self.hass.async_create_task(self.evaluate())

    def stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    def add_listener(self, cb) -> None:
        self._listeners.append(cb)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            cb()

    def _fan_state(self, st) -> bool:
        return fan_running(st.domain, st.state, dict(st.attributes))

    @property
    def fan_on(self) -> bool:
        if not self.fan_entity:
            return False
        st = self.hass.states.get(self.fan_entity)
        return bool(st) and self._fan_state(st)

    async def _on_fan_event(self, event) -> None:
        new = event.data.get("new_state")
        old = event.data.get("old_state")
        now_on = bool(new) and self._fan_state(new)
        was_on = bool(old) and self._fan_state(old)
        if now_on and not was_on:
            self._fan_on_since = time.monotonic()
        elif not now_on:
            self._fan_on_since = None
        await self.evaluate()

    async def _on_tick(self, _now) -> None:
        await self.evaluate()

    # ---------------------------------------------------------------- intent
    async def set_scent(self, on: bool, *, restore: bool = False) -> None:
        """The person's Scent switch (or a restore at start-up)."""
        self.scent_on = on
        if not restore and not self.active:
            await self._write_power(on)
        await self.evaluate()

    def on_power_changed(self, new: bool) -> None:
        """Power changed on the device (push or poll). Ours, or the person's?"""
        if self._pending and self._pending[0] == new and time.monotonic() - self._pending[1] < OWN_WRITE_WINDOW_S:
            self._pending = None
            return
        # someone else (HA power switch, ScentArea app, the unit's button)
        _LOGGER.debug("Power changed to %s outside the HVAC pause: Scent %s", new, "on" if new else "off")
        self.scent_on = new
        self._notify()
        self.hass.async_create_task(self.evaluate())

    # ---------------------------------------------------------------- core
    async def evaluate(self) -> None:
        state = self.coordinator.state
        if state.power is None or self._busy:
            return
        from homeassistant.util import dt as dt_util

        fan_on = self.fan_on
        fan_for = time.monotonic() - self._fan_on_since if (fan_on and self._fan_on_since) else 0.0
        if fan_on and self._fan_on_since is None:
            self._fan_on_since = time.monotonic()
        want, status = decide(
            self.scent_on, self.active, fan_on, scheduled_now(state.schedule, dt_util.now()),
            fan_for, self.start_delay_s, state.power,
        )
        changed = status != self.status
        self.status = status
        if self.active and want is not None and want != state.power:
            await self._write_power(want)
        if status == STATUS_STARTING:
            self._schedule_recheck(max(1.0, self.start_delay_s - fan_for + 0.5))
        if changed:
            self._notify()

    def _schedule_recheck(self, wait_s: float) -> None:
        from homeassistant.helpers.event import async_call_later

        self._unsubs.append(async_call_later(self.hass, wait_s, self._on_tick))

    async def _write_power(self, on: bool) -> None:
        if self.coordinator.state.power == on:
            return
        self._busy = True
        self._pending = (on, time.monotonic())
        try:
            await self.coordinator.async_write_power_for_gate(on)
        except Exception as err:  # noqa: BLE001 - keep the gate alive
            _LOGGER.warning("HVAC pause could not switch the diffuser %s: %s", "on" if on else "off", err)
            self._pending = None
        finally:
            self._busy = False
