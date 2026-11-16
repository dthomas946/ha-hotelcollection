"""Base entity."""

from __future__ import annotations

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import ScentAreaCoordinator


class ScentAreaEntity(CoordinatorEntity[ScentAreaCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: ScentAreaCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=entry.data.get("device_name") or "ScentArea diffuser",
            configuration_url=None,
        )
        self._host = entry.data[CONF_HOST]
