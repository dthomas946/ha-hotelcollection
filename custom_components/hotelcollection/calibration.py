"""Oil calibration: track spraying time since the last refill, correct the rate.

The Villa never measures its oil. It subtracts `rate x hours of spraying` from
the number it was last given (spraying = mode time x spray / (spray + pause)),
so the level is only as good as the rate. This module counts the spraying hours
since the last refill (power on, inside an enabled mode, weighted by that mode's
spray share) and, once you read the real level off the bottle, works out the
rate that would have predicted it:

    rate = (level at refill - level measured now) / spraying hours since refill
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .gate import spray_fraction_now

_LOGGER = logging.getLogger(__name__)

TICK = timedelta(seconds=60)
MAX_GAP_S = 180  # a longer gap (HA down) is not counted as spraying
RATE_MIN, RATE_MAX = 0.1, 25.5
MIN_HOURS_TO_CALIBRATE = 5.0


def calibrated_rate(level_at_refill_ml: float, measured_ml: float, run_hours: float) -> float:
    """Rate in mL per hour of spraying that explains the measured drop."""
    if run_hours < MIN_HOURS_TO_CALIBRATE:
        raise ValueError(
            f"Only {run_hours:.1f} h of spraying since the refill; wait for at least "
            f"{MIN_HOURS_TO_CALIBRATE:.0f} h so the measurement means something"
        )
    used = level_at_refill_ml - measured_ml
    if used <= 0:
        raise ValueError(
            f"Measured {measured_ml:.0f} mL is not below the level at refill "
            f"({level_at_refill_ml:.0f} mL); check both numbers"
        )
    rate = round(used / run_hours, 1)
    if not RATE_MIN <= rate <= RATE_MAX:
        raise ValueError(f"That works out to {rate} mL/h, outside what the Villa accepts (0.1-25.5)")
    return rate


def schedule_hours_between(slots, start: datetime, end: datetime) -> float:
    """Hours of spraying the schedule called for between two local times."""
    minutes = 0.0
    t = start.replace(second=0, microsecond=0)
    while t < end:
        minutes += spray_fraction_now(slots, t)
        t += timedelta(minutes=1)
    return minutes / 60


class OilTracker:
    """Keeps the refill baseline and the spraying hours counted since then."""

    def __init__(self, hass: HomeAssistant, coordinator, entry_id: str) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self._store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.{entry_id}.oil")
        self.refill_at: datetime | None = None
        self.level_at_refill_ml: float | None = None
        self.run_s: float = 0.0
        self.measured_ml: float | None = None
        self.added_ml: float = 500.0
        self.last_calibration: dict[str, Any] | None = None
        self._last_tick: datetime | None = None
        self._unsub = None
        self._listeners: list = []

    # ---- persistence -------------------------------------------------------
    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        if data.get("refill_at"):
            self.refill_at = dt_util.parse_datetime(data["refill_at"])
        self.level_at_refill_ml = data.get("level_at_refill_ml")
        self.run_s = float(data.get("run_s", 0.0))
        self.measured_ml = data.get("measured_ml")
        self.added_ml = float(data.get("added_ml", 500.0))
        self.last_calibration = data.get("last_calibration")

    def _data(self) -> dict[str, Any]:
        return {
            "refill_at": self.refill_at.isoformat() if self.refill_at else None,
            "level_at_refill_ml": self.level_at_refill_ml,
            "run_s": round(self.run_s, 1),
            "measured_ml": self.measured_ml,
            "added_ml": self.added_ml,
            "last_calibration": self.last_calibration,
        }

    def _save(self, now: bool = False) -> None:
        if now:
            self.hass.async_create_task(self._store.async_save(self._data()))
        else:
            self._store.async_delay_save(self._data, 300)
        for cb in list(self._listeners):
            cb()

    def add_listener(self, cb):
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    # ---- counting ----------------------------------------------------------
    def start(self) -> None:
        self._last_tick = dt_util.now()
        self._unsub = async_track_time_interval(self.hass, self._tick, TICK)

    async def async_stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        await self._store.async_save(self._data())

    @callback
    def _tick(self, _now=None) -> None:
        now = dt_util.now()
        gap = (now - self._last_tick).total_seconds() if self._last_tick else 0
        self._last_tick = now
        state = self.coordinator.state
        if self.refill_at is None or not 0 < gap <= MAX_GAP_S:
            return
        share = spray_fraction_now(state.schedule, now) if state.power else 0.0
        if share:
            self.run_s += gap * share
            self._save()

    @property
    def run_hours(self) -> float:
        return self.run_s / 3600

    @property
    def preview_rate(self) -> float | None:
        if self.level_at_refill_ml is None or self.measured_ml is None:
            return None
        try:
            return calibrated_rate(self.level_at_refill_ml, self.measured_ml, self.run_hours)
        except ValueError:
            return None

    # ---- actions -----------------------------------------------------------
    async def async_record_refill(
        self,
        level_ml: float | None,
        at: datetime | None = None,
        run_hours: float | None = None,
        write_device: bool = True,
    ) -> None:
        """Start a new baseline: the bottle held `level_ml` at time `at`."""
        now = dt_util.now()
        at = dt_util.as_local(at) if at else now
        if at > now:
            raise HomeAssistantError("The refill time is in the future")
        if run_hours is None:
            run_hours = schedule_hours_between(self.coordinator.state.schedule, at, now)
        self.refill_at = at
        self.level_at_refill_ml = level_ml
        self.run_s = run_hours * 3600
        self.measured_ml = None
        self._last_tick = now
        self._save(now=True)
        if write_device and level_ml is not None and at == now:
            await self.coordinator.async_set_oil(remaining_ml=level_ml)

    async def async_add_oil(self, added_ml: float | None = None) -> float:
        """Poured `added_ml` (default: Oil to add) into the bottle now; returns the new level."""
        added_ml = self.added_ml if added_ml is None else added_ml
        oil = self.coordinator.state.oil
        if oil is None:
            raise HomeAssistantError("Oil settings not loaded yet")
        level = min(oil.remaining_ml + added_ml, oil.capacity_ml)
        await self.async_record_refill(level)
        return level

    def set_level_at_refill(self, level_ml: float) -> None:
        if self.refill_at is None:
            self.refill_at = dt_util.now()
            self.run_s = 0.0
        self.level_at_refill_ml = level_ml
        self._save(now=True)

    def set_added(self, ml: float) -> None:
        self.added_ml = ml
        self._save(now=True)

    def set_measured(self, level_ml: float) -> None:
        self.measured_ml = level_ml
        self._save(now=True)

    async def async_calibrate(self) -> float:
        """Correct the device's rate from the measured level; returns the new rate."""
        if self.refill_at is None or self.level_at_refill_ml is None:
            raise HomeAssistantError("Set the level at the last refill first")
        if self.measured_ml is None:
            raise HomeAssistantError("Enter the measured oil level first")
        try:
            rate = calibrated_rate(self.level_at_refill_ml, self.measured_ml, self.run_hours)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        oil = self.coordinator.state.oil
        old = oil.rate_ml_h if oil else None
        await self.coordinator.async_set_oil(remaining_ml=self.measured_ml, rate_ml_h=rate)
        self.last_calibration = {
            "at": dt_util.now().isoformat(),
            "old_rate_ml_h": old,
            "new_rate_ml_h": rate,
            "measured_ml": self.measured_ml,
            "run_hours": round(self.run_hours, 1),
        }
        _LOGGER.info("Oil rate calibrated: %s -> %s mL/h", old, rate)
        self._save(now=True)
        return rate
