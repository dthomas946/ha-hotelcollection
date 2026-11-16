"""Power, fan and child-lock switches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import HotelCollectionConfigEntry
from .codec import CMD_FAN, CMD_LOCK, CMD_POWER
from .entity import HotelCollectionEntity


@dataclass(frozen=True, kw_only=True)
class HotelCollectionSwitchDescription(SwitchEntityDescription):
    cmd: int
    attr: str


SWITCHES = (
    HotelCollectionSwitchDescription(key="power", translation_key="power", cmd=CMD_POWER, attr="power"),
    HotelCollectionSwitchDescription(
        key="fan", translation_key="fan", cmd=CMD_FAN, attr="fan", icon="mdi:fan"
    ),
    HotelCollectionSwitchDescription(
        key="child_lock",
        translation_key="child_lock",
        cmd=CMD_LOCK,
        attr="lock",
        icon="mdi:lock",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HotelCollectionConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    entities = [HotelCollectionSwitch(entry.runtime_data, d) for d in SWITCHES]
    entities.append(ScentSwitch(entry.runtime_data))
    async_add_entities(entities)


class HotelCollectionSwitch(HotelCollectionEntity, SwitchEntity):
    entity_description: HotelCollectionSwitchDescription

    def __init__(self, coordinator, description: HotelCollectionSwitchDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return getattr(self.coordinator.data, self.entity_description.attr)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_write(self.entity_description.cmd, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_write(self.entity_description.cmd, 0)


class ScentSwitch(HotelCollectionEntity, SwitchEntity, RestoreEntity):
    """The person's on/off for scenting. With an HVAC fan configured, the
    integration then runs the diffuser only while the fan moves air and a mode
    is scheduled. Turning the diffuser off anywhere else turns this off too."""

    _attr_translation_key = "scent"
    _attr_icon = "mdi:scent"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "scent")

    @property
    def _gate(self):
        return self.coordinator.gate

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in ("on", "off"):
            restored = last.state == "on"
        else:
            restored = bool(self.coordinator.data.power) if self.coordinator.data else True
        await self._gate.set_scent(restored, restore=True)
        self._gate.add_listener(self.async_write_ha_state)

    @property
    def is_on(self) -> bool:
        return self._gate.scent_on

    @property
    def extra_state_attributes(self):
        return {"hvac_pause": self._gate.active, "status": self._gate.status}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._gate.set_scent(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._gate.set_scent(False)
        self.async_write_ha_state()
