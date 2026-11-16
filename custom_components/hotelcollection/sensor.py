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
from .codec import DeviceState, spray_hours_per_day
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
    async_add_entities(HotelCollectionSensor(entry.runtime_data, d) for d in SENSORS)


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
