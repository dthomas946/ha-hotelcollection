"""Oil, consumption and schedule sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import HotelCollectionConfigEntry
from .codec import DeviceState, spray_hours_per_day, to_oz
from .gate import STATUSES
from .entity import HotelCollectionEntity


def _hours_left(s: DeviceState) -> float | None:
    if not s.oil or not s.oil.rate_ml_h:
        return None
    return round(s.oil.remaining_ml / s.oil.rate_ml_h, 1)


def _active_slots(s: DeviceState) -> int:
    return sum(1 for slot in s.schedule if slot.enabled)


def _clock(s: DeviceState):
    if s.clock is None:
        return None
    return s.clock.replace(tzinfo=dt_util.get_default_time_zone())


@dataclass(frozen=True, kw_only=True)
class HotelCollectionSensorDescription(SensorEntityDescription):
    value_fn: Callable[[DeviceState], Any]
    attrs_fn: Callable[[DeviceState], dict[str, Any]] | None = None


SENSORS = (
    HotelCollectionSensorDescription(
        key="oil_remaining",
        translation_key="oil_remaining",
        native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        suggested_unit_of_measurement=UnitOfVolume.MILLILITERS,
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:bottle-tonic-outline",
        value_fn=lambda s: s.oil.remaining_ml if s.oil else None,
        attrs_fn=lambda s: {"fl_oz": to_oz(s.oil.remaining_ml)} if s.oil else {},
    ),
    HotelCollectionSensorDescription(
        key="oil_to_fill",
        translation_key="oil_to_fill",
        native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        suggested_unit_of_measurement=UnitOfVolume.MILLILITERS,
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cart-arrow-down",
        value_fn=lambda s: s.oil.to_fill_ml if s.oil else None,
        attrs_fn=lambda s: {
            "fl_oz": to_oz(s.oil.to_fill_ml),
            "max_fill_ml": s.oil.max_fill_ml,
            "max_fill_fl_oz": to_oz(s.oil.max_fill_ml),
        } if s.oil else {},
    ),
    HotelCollectionSensorDescription(
        key="oil_level",
        translation_key="oil_level",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        value_fn=lambda s: s.oil.percent if s.oil else None,
    ),
    HotelCollectionSensorDescription(
        key="oil_capacity",
        translation_key="oil_capacity",
        native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        suggested_unit_of_measurement=UnitOfVolume.MILLILITERS,
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.oil.capacity_ml if s.oil else None,
        attrs_fn=lambda s: {"fl_oz": to_oz(s.oil.capacity_ml)} if s.oil else {},
    ),
    HotelCollectionSensorDescription(
        key="consumption_rate",
        translation_key="consumption_rate",
        native_unit_of_measurement="mL/h",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
        value_fn=lambda s: s.oil.rate_ml_h if s.oil else None,
    ),
    HotelCollectionSensorDescription(
        key="hours_remaining",
        translation_key="hours_remaining",
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-sand",
        value_fn=_hours_left,
    ),
    HotelCollectionSensorDescription(
        key="days_left",
        translation_key="days_left",
        native_unit_of_measurement=UnitOfTime.DAYS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-end",
        value_fn=lambda s: s.days_left,
        attrs_fn=lambda s: {
            "spray_hours_per_day": round(spray_hours_per_day(s.schedule), 2),
            "device_estimate": s.device_days_left,
        },
    ),
    HotelCollectionSensorDescription(
        key="schedule",
        translation_key="schedule",
        icon="mdi:calendar-clock",
        value_fn=_active_slots,
        attrs_fn=lambda s: {"slots": [slot.as_dict() for slot in s.schedule]},
    ),
    HotelCollectionSensorDescription(
        key="device_clock",
        translation_key="device_clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_clock,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HotelCollectionConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    entities = [HotelCollectionSensor(entry.runtime_data, d) for d in SENSORS]
    entities.append(ScentStatusSensor(entry.runtime_data))
    entities.append(SprayTimeSinceRefillSensor(entry.runtime_data))
    async_add_entities(entities)


class HotelCollectionSensor(HotelCollectionEntity, SensorEntity):
    entity_description: HotelCollectionSensorDescription

    def __init__(self, coordinator, description: HotelCollectionSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn:
            return self.entity_description.attrs_fn(self.coordinator.data)
        return None



class ScentStatusSensor(HotelCollectionEntity, SensorEntity):
    """Why the diffuser is or isn't spraying right now."""

    _attr_translation_key = "scent_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES
    _attr_icon = "mdi:scent"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "scent_status")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.coordinator.gate.add_listener(self.async_write_ha_state)

    @property
    def native_value(self) -> str:
        return self.coordinator.gate.status

    @property
    def extra_state_attributes(self):
        gate = self.coordinator.gate
        return {"hvac_fan_entity": gate.fan_entity, "hvac_fan_running": gate.fan_on if gate.active else None}


class SprayTimeSinceRefillSensor(HotelCollectionEntity, SensorEntity):
    """Hours of spraying since the last refill; the basis for calibrating the rate."""

    _attr_translation_key = "spray_time_since_refill"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:timer-sand"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "spray_time_since_refill")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.oil_tracker.add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> float | None:
        t = self.coordinator.oil_tracker
        return round(t.run_hours, 2) if t.refill_at else None

    @property
    def extra_state_attributes(self):
        t = self.coordinator.oil_tracker
        used = None
        if t.level_at_refill_ml is not None and t.measured_ml is not None:
            used = round(t.level_at_refill_ml - t.measured_ml, 1)
        cal = t.last_calibration or {}
        return {
            "refilled_at": t.refill_at.isoformat() if t.refill_at else None,
            "level_at_refill_ml": t.level_at_refill_ml,
            "measured_ml": t.measured_ml,
            "used_ml": used,
            "calibrated_rate_preview": t.preview_rate,
            "last_calibrated_at": cal.get("at"),
            "last_calibration_old_rate": cal.get("old_rate_ml_h"),
            "last_calibration_new_rate": cal.get("new_rate_ml_h"),
            "calibrations": len(t.history),
            "calibration_history": [
                {
                    "date": h.get("at", "")[:10],
                    "rate_ml_h": h.get("new_rate_ml_h"),
                    "used_ml": round(h["level_at_refill_ml"] - h["measured_ml"], 1)
                    if h.get("level_at_refill_ml") is not None and h.get("measured_ml") is not None
                    else None,
                    "spray_hours": h.get("run_hours"),
                }
                for h in t.history
            ],
        }
