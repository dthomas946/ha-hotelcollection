"""Coordinator: periodic polling plus instant push updates."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import HotelCollectionClient, HotelCollectionError
from .codec import (
    ALL_SLOTS,
    CMD_CLOCK,
    CMD_FAN,
    CMD_LOCK,
    CMD_NAME,
    CMD_OIL,
    CMD_POWER,
    CMD_SCHEDULE,
    DeviceState,
    Frame,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

POLL_CMDS = (CMD_POWER, CMD_FAN, CMD_LOCK, CMD_OIL, CMD_CLOCK)


class HotelCollectionCoordinator(DataUpdateCoordinator[DeviceState]):
    """Owns the client and the decoded device state."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, host: str, port: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {host}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.state = DeviceState()
        self.client = HotelCollectionClient(host, port, self._handle_frame)

    @callback
    def _handle_frame(self, frame: Frame) -> None:
        """Push path: status changes made from the app, buttons or HA."""
        if self.state.apply(frame) and self.data is not None:
            self.async_set_updated_data(self.state)

    async def _async_update_data(self) -> DeviceState:
        try:
            if self.state.name is None:
                await self.client.read(CMD_NAME)
            for cmd in POLL_CMDS:
                await self.client.read(cmd)
            # without a slot mask the device returns an arbitrary subset of slots
            await self.client.read(CMD_SCHEDULE, bytes([ALL_SLOTS]))
        except HotelCollectionError as err:
            await self.client.close()
            raise UpdateFailed(str(err)) from err
        return self.state

    async def async_write(self, cmd: int, value: int) -> None:
        try:
            await self.client.write(cmd, value)
        except HotelCollectionError as err:
            await self.client.close()
            raise HomeAssistantError(f"Diffuser did not accept the command: {err}") from err
        # the device follows the ACK with an S status push; read back as a fallback
        try:
            await self.client.read(cmd)
        except HotelCollectionError:
            pass
        self.async_set_updated_data(self.state)

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self.client.close()
