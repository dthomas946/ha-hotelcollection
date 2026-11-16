"""Add oil and Calibrate rate buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HotelCollectionConfigEntry
from .entity import HotelCollectionEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HotelCollectionConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    c = entry.runtime_data
    async_add_entities([AddOilButton(c), CalibrateButton(c)])


class AddOilButton(HotelCollectionEntity, ButtonEntity):
    """Poured "Oil to add" into the bottle: level += that, capped at the bottle size.

    Keeps the old key so the entity id (button.<name>_oil_refilled) does not change.
    """

    _attr_translation_key = "oil_refilled"
    _attr_icon = "mdi:bottle-tonic-plus-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "oil_refilled")

    async def async_press(self) -> None:
        await self.coordinator.oil_tracker.async_add_oil()


class CalibrateButton(HotelCollectionEntity, ButtonEntity):
    _attr_translation_key = "calibrate_rate"
    _attr_icon = "mdi:tune-variant"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "calibrate_rate")

    async def async_press(self) -> None:
        await self.coordinator.oil_tracker.async_calibrate()
