"""Hotel Collection: cloud-free control of Hotel Collection scent diffusers (ScentArea app family)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .const import DEFAULT_PORT
from .coordinator import HotelCollectionCoordinator

PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.TEXT]

type HotelCollectionConfigEntry = ConfigEntry[HotelCollectionCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: HotelCollectionConfigEntry) -> bool:
    coordinator = HotelCollectionCoordinator(
        hass, entry, entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT)
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HotelCollectionConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.close()
    return unloaded
