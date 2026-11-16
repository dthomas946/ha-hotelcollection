"""HVAC fan source as a setting on the device page (also settable by voice/AI)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HotelCollectionConfigEntry
from .const import CONF_HVAC_FAN_ENTITY
from .entity import HotelCollectionEntity

NONE = "none"
# domains always offered; for the others only entities that look like a fan or blower
ALWAYS = ("climate", "fan")
IF_NAMED = ("binary_sensor", "sensor", "switch", "input_boolean")
WORDS = ("fan", "blower", "hvac", "furnace", "air_handler")


def fan_candidates(hass: HomeAssistant, current: str | None) -> list[str]:
    found = []
    for state in hass.states.async_all():
        domain = state.domain
        name = f"{state.entity_id} {state.name}".lower().replace(" ", "_")
        if domain in ALWAYS or (domain in IF_NAMED and any(w in name for w in WORDS)):
            found.append(state.entity_id)
    if current and current not in found:
        found.append(current)
    return [NONE, *sorted(found)]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HotelCollectionConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([HvacFanSelect(entry.runtime_data)])


class HvacFanSelect(HotelCollectionEntity, SelectEntity):
    """Which entity tells the integration the HVAC fan is running ("none" = pause off).

    Same setting as Configure on the integration; changing it reloads the integration.
    """

    _attr_translation_key = "hvac_fan_source"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:hvac"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "hvac_fan_source")

    @property
    def available(self) -> bool:
        return True

    @property
    def options(self) -> list[str]:
        return fan_candidates(self.hass, self.coordinator.config_entry.options.get(CONF_HVAC_FAN_ENTITY))

    @property
    def current_option(self) -> str:
        return self.coordinator.config_entry.options.get(CONF_HVAC_FAN_ENTITY) or NONE

    async def async_select_option(self, option: str) -> None:
        entry = self.coordinator.config_entry
        opts = dict(entry.options)
        if option == NONE:
            opts.pop(CONF_HVAC_FAN_ENTITY, None)
        else:
            opts[CONF_HVAC_FAN_ENTITY] = option
        self.hass.config_entries.async_update_entry(entry, options=opts)
