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
    ScheduleSlot,
    days_to_mask,
    encode_oil,
    encode_slot,
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
        self.gate = None  # set by async_setup_entry (gate.ScentGate)

    @callback
    def _handle_frame(self, frame: Frame) -> None:
        """Every frame (replies and pushes): update state, tell the HVAC pause."""
        old_power = self.state.power
        old_schedule = list(self.state.schedule)
        changed = self.state.apply(frame)
        if self.gate is not None:
            if old_power is not None and self.state.power is not None and self.state.power != old_power:
                self.gate.on_power_changed(self.state.power)
            elif self.state.schedule != old_schedule:
                self.hass.async_create_task(self.gate.evaluate())
        if changed and self.data is not None:
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

    async def async_write_power_for_gate(self, on: bool) -> None:
        """Power write made by the HVAC pause (not the person)."""
        await self.client.write(CMD_POWER, 1 if on else 0)
        try:
            await self.client.read(CMD_POWER)
        except HotelCollectionError:
            pass
        self.async_set_updated_data(self.state)

    async def async_set_mode(self, mode: int, **changes) -> None:
        """Change one schedule mode; fields not given keep their current value."""
        current = next((s for s in self.state.schedule if s.slot == mode), None)
        if current is None:
            raise HomeAssistantError(f"Mode {mode} is unknown; schedule not loaded yet")
        slot = ScheduleSlot(
            slot=mode,
            days_mask=days_to_mask(changes["days"]) if "days" in changes else current.days_mask,
            start=changes.get("start", current.start),
            end=changes.get("end", current.end),
            enabled=changes.get("enabled", current.enabled),
            work_s=int(changes.get("spray_seconds", current.work_s)),
            pause_s=int(changes.get("pause_seconds", current.pause_s)),
        )
        try:
            payload = encode_slot(slot)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        try:
            await self.client.write_payload(CMD_SCHEDULE, payload)
            await self.client.read(CMD_SCHEDULE, bytes([ALL_SLOTS]))
        except HotelCollectionError as err:
            await self.client.close()
            raise HomeAssistantError(f"Diffuser did not accept the schedule change: {err}") from err
        self.async_set_updated_data(self.state)

    async def async_set_oil(self, *, capacity_ml=None, remaining_ml=None, rate_ml_h=None) -> None:
        """Change bottle size, oil remaining and/or consumption rate (others kept)."""
        oil = self.state.oil
        if oil is None:
            raise HomeAssistantError("Oil settings not loaded yet")
        capacity = int(capacity_ml if capacity_ml is not None else oil.capacity_ml)
        remaining = int(remaining_ml if remaining_ml is not None else oil.remaining_ml)
        rate = float(rate_ml_h if rate_ml_h is not None else oil.rate_ml_h)
        if capacity_ml is not None and remaining_ml is None:
            remaining = min(remaining, capacity)
        try:
            payload = encode_oil(capacity, remaining, rate)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        try:
            await self.client.write_payload(CMD_OIL, payload)
            await self.client.read(CMD_OIL)
        except HotelCollectionError as err:
            await self.client.close()
            raise HomeAssistantError(f"Diffuser did not accept the oil settings: {err}") from err
        self.async_set_updated_data(self.state)

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self.client.close()
