"""Editable oil settings: consumption rate, oil remaining, bottle size."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import EntityCategory, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HotelCollectionConfigEntry
from .codec import DeviceState
from .const import CONF_START_DELAY, DEFAULT_START_DELAY
from .entity import HotelCollectionEntity


@dataclass(frozen=True, kw_only=True)
class HotelCollectionNumberDescription(NumberEntityDescription):
    value_fn: Callable[[DeviceState], float | None]
    field: str  # keyword for coordinator.async_set_oil
    max_fn: Callable[[DeviceState], float] | None = None


NUMBERS = (
    HotelCollectionNumberDescription(
        key="consumption_rate_setting",
        translation_key="consumption_rate_setting",
        native_unit_of_measurement="mL/h",
        native_min_value=0.1,
        native_max_value=25.5,
        native_step=0.1,
        mode=NumberMode.BOX,
        icon="mdi:speedometer",
        field="rate_ml_h",
        value_fn=lambda s: s.oil.rate_ml_h if s.oil else None,
    ),
    HotelCollectionNumberDescription(
        key="oil_remaining_setting",
        translation_key="oil_remaining_setting",
        native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        native_min_value=0,
        native_max_value=65535,
        native_step=1,
        mode=NumberMode.BOX,
        icon="mdi:bottle-tonic-outline",
        field="remaining_ml",
        value_fn=lambda s: s.oil.remaining_ml if s.oil else None,
        max_fn=lambda s: s.oil.capacity_ml if s.oil else 65535,
    ),
    HotelCollectionNumberDescription(
        key="bottle_size_setting",
        translation_key="bottle_size_setting",
        native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        native_min_value=10,
        native_max_value=5000,
        native_step=10,
        mode=NumberMode.BOX,
        icon="mdi:bottle-tonic",
        entity_category=EntityCategory.CONFIG,
        field="capacity_ml",
        value_fn=lambda s: s.oil.capacity_ml if s.oil else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HotelCollectionConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    c = entry.runtime_data
    async_add_entities(
        [HotelCollectionNumber(c, d) for d in NUMBERS]
        + [TrackerNumber(c, d) for d in TRACKER_NUMBERS]
        + [HvacStartDelayNumber(c)]
    )


class HotelCollectionNumber(HotelCollectionEntity, NumberEntity):
    entity_description: HotelCollectionNumberDescription

    def __init__(self, coordinator, description: HotelCollectionNumberDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def native_max_value(self) -> float:
        if self.entity_description.max_fn:
            return self.entity_description.max_fn(self.coordinator.data)
        return self.entity_description.native_max_value

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_oil(**{self.entity_description.field: value})


@dataclass(frozen=True, kw_only=True)
class TrackerNumberDescription(NumberEntityDescription):
    value_fn: Callable[[object], float | None]
    set_fn: Callable[[object, float], None]


TRACKER_NUMBERS = (
    TrackerNumberDescription(
        key="oil_to_add",
        translation_key="oil_to_add",
        native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        native_min_value=10,
        native_max_value=5000,
        native_step=10,
        mode=NumberMode.BOX,
        icon="mdi:bottle-tonic-plus",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda t: t.added_ml,
        set_fn=lambda t, v: t.set_added(v),
    ),
    TrackerNumberDescription(
        key="level_at_refill",
        translation_key="level_at_refill",
        native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        native_min_value=0,
        native_max_value=5000,
        native_step=1,
        mode=NumberMode.BOX,
        icon="mdi:bottle-tonic",
        value_fn=lambda t: t.level_at_refill_ml,
        set_fn=lambda t, v: t.set_level_at_refill(v),
    ),
    TrackerNumberDescription(
        key="measured_oil_level",
        translation_key="measured_oil_level",
        native_unit_of_measurement=UnitOfVolume.MILLILITERS,
        native_min_value=0,
        native_max_value=5000,
        native_step=1,
        mode=NumberMode.BOX,
        icon="mdi:ruler",
        value_fn=lambda t: t.measured_ml,
        set_fn=lambda t, v: t.set_measured(v),
    ),
)


class TrackerNumber(HotelCollectionEntity, NumberEntity):
    """Calibration inputs, kept by the integration (not on the device)."""

    entity_description: TrackerNumberDescription

    def __init__(self, coordinator, description: TrackerNumberDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.oil_tracker.add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator.oil_tracker)

    async def async_set_native_value(self, value: float) -> None:
        self.entity_description.set_fn(self.coordinator.oil_tracker, value)


class HvacStartDelayNumber(HotelCollectionEntity, NumberEntity):
    """Seconds the HVAC fan must run before spraying starts (same as Configure)."""

    _attr_translation_key = "hvac_start_delay"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = "s"
    _attr_native_min_value = 0
    _attr_native_max_value = 300
    _attr_native_step = 5
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:timer-play-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "hvac_start_delay")

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> float:
        return float(self.coordinator.config_entry.options.get(CONF_START_DELAY, DEFAULT_START_DELAY))

    async def async_set_native_value(self, value: float) -> None:
        entry = self.coordinator.config_entry
        self.hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_START_DELAY: int(value)}
        )
