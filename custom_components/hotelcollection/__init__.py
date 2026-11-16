"""Hotel Collection: cloud-free control of Hotel Collection scent diffusers (ScentArea app family)."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .codec import DAY_NAMES, SPRAY_MAX_S, SPRAY_MIN_S
from .const import CONF_HVAC_FAN_ENTITY, CONF_START_DELAY, DEFAULT_PORT, DEFAULT_START_DELAY, DOMAIN
from .calibration import OilTracker
from .gate import ScentGate
from .coordinator import HotelCollectionCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BUTTON, Platform.NUMBER, Platform.SELECT, Platform.SENSOR, Platform.SWITCH, Platform.TEXT,
]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
CARD_URL = f"/{DOMAIN}/hotelcollection-card.js"

type HotelCollectionConfigEntry = ConfigEntry[HotelCollectionCoordinator]

SERVICE_SET_MODE = "set_mode"
SERVICE_RECORD_REFILL = "record_refill"


def _day(value: str) -> str:
    day = str(value).strip()[:3].title()
    if day not in DAY_NAMES:
        raise vol.Invalid(f"unknown day {value!r}; use Mon..Sun")
    return day


def _hhmm(value) -> str:
    return cv.time(value).strftime("%H:%M")


SET_MODE_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
        vol.Required("mode"): vol.All(vol.Coerce(int), vol.Range(min=1, max=5)),
        vol.Optional("enabled"): cv.boolean,
        vol.Optional("days"): vol.All(cv.ensure_list, [_day]),
        vol.Optional("start"): _hhmm,
        vol.Optional("end"): _hhmm,
        vol.Optional("spray_seconds"): vol.All(vol.Coerce(int), vol.Range(min=SPRAY_MIN_S, max=SPRAY_MAX_S)),
        vol.Optional("pause_seconds"): vol.All(vol.Coerce(int), vol.Range(min=SPRAY_MIN_S, max=SPRAY_MAX_S)),
    }
)


RECORD_REFILL_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
        vol.Optional("level_ml"): vol.All(vol.Coerce(float), vol.Range(min=0, max=5000)),
        vol.Optional("refilled_at"): cv.datetime,
        vol.Optional("run_hours"): vol.All(vol.Coerce(float), vol.Range(min=0)),
    }
)


def _entry(hass: HomeAssistant, entry_id: str | None):
    entries = [
        e for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED and (entry_id is None or e.entry_id == entry_id)
    ]
    if not entries:
        raise ServiceValidationError("No loaded Hotel Collection diffuser found")
    if entry_id is None and len(entries) > 1:
        raise ServiceValidationError("Several diffusers are set up: give config_entry_id")
    return entries[0]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the dashboard card and load it on every dashboard."""
    integration = await async_get_integration(hass, DOMAIN)
    card = Path(__file__).parent / "www" / "hotelcollection-card.js"
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(card), cache_headers=False)]
        )
    except RuntimeError:
        _LOGGER.debug("Card path already registered")
    # version query string makes browsers fetch the new card after an update
    add_extra_js_url(hass, f"{CARD_URL}?v={integration.version}")

    async def set_mode(call: ServiceCall) -> None:
        data = dict(call.data)
        entry = _entry(hass, data.pop("config_entry_id", None))
        mode = data.pop("mode")
        await entry.runtime_data.async_set_mode(mode, **data)

    async def record_refill(call: ServiceCall) -> None:
        entry = _entry(hass, call.data.get("config_entry_id"))
        await entry.runtime_data.oil_tracker.async_record_refill(
            call.data.get("level_ml"),
            at=call.data.get("refilled_at"),
            run_hours=call.data.get("run_hours"),
        )

    hass.services.async_register(DOMAIN, SERVICE_SET_MODE, set_mode, schema=SET_MODE_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_RECORD_REFILL, record_refill, schema=RECORD_REFILL_SCHEMA
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HotelCollectionConfigEntry) -> bool:
    coordinator = HotelCollectionCoordinator(
        hass, entry, entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT)
    )
    await coordinator.async_config_entry_first_refresh()
    coordinator.gate = ScentGate(
        hass,
        coordinator,
        entry.options.get(CONF_HVAC_FAN_ENTITY),
        float(entry.options.get(CONF_START_DELAY, DEFAULT_START_DELAY)),
    )
    coordinator.oil_tracker = OilTracker(hass, coordinator, entry.entry_id)
    await coordinator.oil_tracker.async_load()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # start after the Scent switch has restored the person's last choice
    coordinator.gate.start()
    entry.async_on_unload(coordinator.gate.stop)
    coordinator.oil_tracker.start()
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: HotelCollectionConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HotelCollectionConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.oil_tracker.async_stop()
        await entry.runtime_data.client.close()
    return unloaded
