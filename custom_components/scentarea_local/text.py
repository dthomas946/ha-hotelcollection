"""Scent name: kept in HA because the diffuser does not store it."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import ScentAreaConfigEntry
from .entity import ScentAreaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ScentAreaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([ScentNameText(entry.runtime_data)])


class ScentNameText(ScentAreaEntity, TextEntity, RestoreEntity):
    _attr_translation_key = "scent"
    _attr_icon = "mdi:scent"
    _attr_native_max = 64

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "scent")
        self._attr_native_value = ""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state not in ("unknown", "unavailable"):
            self._attr_native_value = last.state

    @property
    def available(self) -> bool:
        return True  # a local label; usable even if the diffuser is offline

    async def async_set_value(self, value: str) -> None:
        self._attr_native_value = value.strip()
        self.async_write_ha_state()
