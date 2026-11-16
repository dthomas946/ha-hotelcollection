"""Oil refilled: set oil remaining to the bottle size."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HotelCollectionConfigEntry
from .entity import HotelCollectionEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HotelCollectionConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([OilRefilledButton(entry.runtime_data)])


class OilRefilledButton(HotelCollectionEntity, ButtonEntity):
    _attr_translation_key = "oil_refilled"
    _attr_icon = "mdi:bottle-tonic-plus-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "oil_refilled")

    async def async_press(self) -> None:
        oil = self.coordinator.data.oil
        if oil is None:
            raise HomeAssistantError("Oil settings not loaded yet")
        await self.coordinator.async_set_oil(remaining_ml=oil.capacity_ml)
