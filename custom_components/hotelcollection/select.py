"""HVAC fan source as a setting on the device page (also settable by voice/AI)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HotelCollectionConfigEntry
from .const import CONF_HVAC_FAN_ENTITY
from .entity import HotelCollectionEntity

NONE = "none"
# domains always offered; for the others only entities that look like a fan or blower
ALWAYS = ("climate", "fan")
IF_NAMED = ("binary_sensor", "sensor", "switch", "input_boolean")
WORDS = ("blower", "_fan", "fan_", "air_handler", "furnace")
SKIP = ("hours", "total", "time", "count", "filter", "rssi", "lqi", "continuous")


def fan_candidates(hass: HomeAssistant, current: str | None, own: set[str] = frozenset()) -> list[str]:
    found = []
    for state in hass.states.async_all():
        domain = state.domain
        if state.entity_id in own:
            continue
        oid = state.entity_id.split(".", 1)[1]
        name = f"_{oid}_"
        if domain in ALWAYS or (
            domain in IF_NAMED
            and any(w in name for w in WORDS)
            and not any(w in oid for w in SKIP)
        ):
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
        own = {
            e.entity_id
            for e in er.async_entries_for_config_entry(
                er.async_get(self.hass), self.coordinator.config_entry.entry_id
            )
        }
        return fan_candidates(
            self.hass, self.coordinator.config_entry.options.get(CONF_HVAC_FAN_ENTITY), own
        )

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
