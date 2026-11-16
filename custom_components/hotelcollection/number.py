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
    async_add_entities(HotelCollectionNumber(entry.runtime_data, d) for d in NUMBERS)


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
