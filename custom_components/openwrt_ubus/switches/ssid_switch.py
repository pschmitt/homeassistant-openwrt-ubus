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

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as exc:
        _LOGGER.warning("Initial SSID data fetch failed for %s: %s", entry.data[CONF_HOST], exc)
        return

    ssid_data = coordinator.data.get("ssid_status", {})
    if not ssid_data:
        _LOGGER.warning("No wireless interfaces found on %s", entry.data[CONF_HOST])
        return

    entities = [
        OpenwrtSSIDSwitch(coordinator, section_name, iface_data, entry)
        for section_name, iface_data in ssid_data.items()
        if isinstance(iface_data, dict) and iface_data.get("mode", "ap") == "ap"
    ]

    if entities:
        async_add_entities(entities, True)
        _LOGGER.info(
            "Created %d SSID switch entities for %s",
            len(entities),
            entry.data[CONF_HOST],
        )


class OpenwrtSSIDSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable or disable a WiFi SSID on an OpenWrt AP."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SharedDataUpdateCoordinator,
        section_name: str,
        iface_data: dict,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the SSID switch."""
        super().__init__(coordinator)
        self._section_name = section_name
        self._host = entry.data[CONF_HOST]
        self._attr_unique_id = f"{DOMAIN}_{self._host}_ssid_{section_name}"
        self._optimistic_state: bool | None = None
        # Store initial SSID name; updated dynamically from coordinator data.
        self._ssid = iface_data.get("ssid", section_name)
        self._radio = iface_data.get("device", "")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _iface_data(self) -> dict:
        ssid_status = self.coordinator.data.get("ssid_status", {})
        return ssid_status.get(self._section_name, {})

    # ------------------------------------------------------------------
    # Entity properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        data = self._iface_data()
        ssid = data.get("ssid", self._ssid)
        radio = data.get("device", self._radio)
        # Append the radio suffix so per-band switches are distinguishable
        # e.g. "brkn-lan (radio0)" vs "brkn-lan (radio1)"
        return f"{ssid} ({radio})" if radio else ssid

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
        return not self._iface_data().get("disabled", False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._iface_data()
        return {
            "section": self._section_name,
            "radio": data.get("device", self._radio),
            "ssid": data.get("ssid", self._ssid),
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
        """Enable the SSID."""
        await self._set_disabled(False)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the SSID."""
        await self._set_disabled(True)

    async def _set_disabled(self, disabled: bool) -> None:
        self._optimistic_state = not disabled
        self.async_write_ha_state()
        try:
            ubus = await self.coordinator.data_manager.get_ubus_connection_async()
            await ubus.uci_set_option(
                "wireless", self._section_name, "disabled", "1" if disabled else "0"
            )
            await ubus.uci_commit_config("wireless")
            await ubus.wifi_reload()
            _LOGGER.info(
                "SSID %s (%s) on %s: %s",
                self._ssid,
                self._section_name,
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
