"""Power, fan and child-lock switches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ScentAreaConfigEntry
from .codec import CMD_FAN, CMD_LOCK, CMD_POWER
from .entity import ScentAreaEntity


@dataclass(frozen=True, kw_only=True)
class ScentAreaSwitchDescription(SwitchEntityDescription):
    cmd: int
    attr: str


SWITCHES = (
    ScentAreaSwitchDescription(key="power", translation_key="power", cmd=CMD_POWER, attr="power"),
    ScentAreaSwitchDescription(
        key="fan", translation_key="fan", cmd=CMD_FAN, attr="fan", icon="mdi:fan"
    ),
    ScentAreaSwitchDescription(
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
    entry: ScentAreaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(ScentAreaSwitch(entry.runtime_data, d) for d in SWITCHES)


class ScentAreaSwitch(ScentAreaEntity, SwitchEntity):
    entity_description: ScentAreaSwitchDescription

    def __init__(self, coordinator, description: ScentAreaSwitchDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return getattr(self.coordinator.data, self.entity_description.attr)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_write(self.entity_description.cmd, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_write(self.entity_description.cmd, 0)
