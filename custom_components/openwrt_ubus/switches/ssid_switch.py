"""SSID enable/disable switch for OpenWrt ubus integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN, CONF_ENABLE_SSID_SWITCHES, DEFAULT_ENABLE_SSID_SWITCHES
from ..shared_data_manager import SharedDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SSID switch entities from a config entry."""
    if not entry.data.get(CONF_ENABLE_SSID_SWITCHES, DEFAULT_ENABLE_SSID_SWITCHES):
        _LOGGER.debug("SSID switches disabled, skipping setup")
        return

    data_manager_key = f"data_manager_{entry.entry_id}"
    data_manager = hass.data[DOMAIN][data_manager_key]

    coordinator = SharedDataUpdateCoordinator(
        hass,
        data_manager,
        ["ssid_status"],
        f"{DOMAIN}_ssid_{entry.data[CONF_HOST]}",
        SCAN_INTERVAL,
    )

    created_ssids = set()

    async def _add_ssid_switches() -> None:
        ssid_data = coordinator.data.get("ssid_status", {}) if coordinator.data else {}
        if not ssid_data:
            _LOGGER.warning("No wireless interfaces found on %s", entry.data[CONF_HOST])
            return

        # Group UCI sections by SSID name so we get one switch per SSID
        # (each SSID typically has one section per radio band).
        ssid_groups: dict[str, list[str]] = {}
        for section_name, iface_data in ssid_data.items():
            if not isinstance(iface_data, dict) or iface_data.get("mode", "ap") != "ap":
                continue
            ssid = iface_data.get("ssid", section_name)
            if ssid in created_ssids:
                continue
            ssid_groups.setdefault(ssid, []).append(section_name)

        entities = [
            OpenwrtSSIDSwitch(coordinator, ssid, sections, entry)
            for ssid, sections in ssid_groups.items()
        ]

        if entities:
            async_add_entities(entities, False)
            created_ssids.update(ssid_groups)
            _LOGGER.info(
                "Created %d SSID switch entities for %s",
                len(entities),
                entry.data[CONF_HOST],
            )

    def _handle_coordinator_update() -> None:
        hass.async_create_task(_add_ssid_switches())

    coordinator.async_add_listener(_handle_coordinator_update)

    async def _refresh_ssids() -> None:
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception as exc:
            _LOGGER.warning("Initial SSID data fetch failed for %s: %s", entry.data[CONF_HOST], exc)

    hass.async_create_task(_refresh_ssids())


class OpenwrtSSIDSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable or disable a WiFi SSID on an OpenWrt AP.

    One switch per SSID; toggling it updates all UCI sections that share
    that SSID name (i.e. the same network on both 2.4 GHz and 5 GHz).
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SharedDataUpdateCoordinator,
        ssid: str,
        sections: list[str],
        entry: ConfigEntry,
    ) -> None:
        """Initialize the SSID switch."""
        super().__init__(coordinator)
        self._ssid = ssid
        self._sections = sections  # all UCI sections that belong to this SSID
        self._host = entry.data[CONF_HOST]
        # Unique ID based on SSID name; stable across radio changes.
        self._attr_unique_id = f"{DOMAIN}_{self._host}_ssid_{ssid}"
        self._optimistic_state: bool | None = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _sections_data(self) -> list[dict]:
        ssid_status = self.coordinator.data.get("ssid_status", {})
        return [ssid_status[s] for s in self._sections if s in ssid_status]

    # ------------------------------------------------------------------
    # Entity properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._ssid

    @property
    def icon(self) -> str:
        return "mdi:wifi" if self.is_on else "mdi:wifi-off"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self._host)})

    @property
    def is_on(self) -> bool:
        if self._optimistic_state is not None:
            return self._optimistic_state
        sections = self._sections_data()
        if not sections:
            return False
        # On = at least one band is enabled (disabled=False)
        return any(not s.get("disabled", False) for s in sections)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "ssid": self._ssid,
            "sections": self._sections,
            "radios": [s.get("device", "") for s in self._sections_data()],
        }

    # ------------------------------------------------------------------
    # Coordinator callback
    # ------------------------------------------------------------------

    @callback
    def _handle_coordinator_update(self) -> None:
        self._optimistic_state = None
        super()._handle_coordinator_update()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the SSID on all bands."""
        await self._set_disabled(False)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the SSID on all bands."""
        await self._set_disabled(True)

    async def _set_disabled(self, disabled: bool) -> None:
        self._optimistic_state = not disabled
        self.async_write_ha_state()
        try:
            ubus = await self.coordinator.data_manager.get_ubus_connection_async()
            for section in self._sections:
                await ubus.uci_set_option(
                    "wireless", section, "disabled", "1" if disabled else "0"
                )
            await ubus.uci_commit_config("wireless")
            await ubus.wifi_reload()
            _LOGGER.info(
                "SSID %s (%s) on %s: %s",
                self._ssid,
                ", ".join(self._sections),
                self._host,
                "disabled" if disabled else "enabled",
            )
        except Exception as exc:
            self._optimistic_state = None
            self.async_write_ha_state()
            raise HomeAssistantError(
                f"Failed to {'disable' if disabled else 'enable'} SSID {self._ssid}: {exc}"
            ) from exc

        self.coordinator.data_manager.invalidate_cache("ssid_status")

        async def _delayed_refresh() -> None:
            await asyncio.sleep(5)
            await self.coordinator.async_request_refresh()

        self.hass.async_create_task(_delayed_refresh())
