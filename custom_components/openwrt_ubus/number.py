"""Support for OpenWrt router number entities."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .shared_data_manager import SharedDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities from a config entry."""
    data_manager_key = f"data_manager_{entry.entry_id}"
    data_manager = hass.data[DOMAIN][data_manager_key]

    coordinator = SharedDataUpdateCoordinator(
        hass,
        data_manager,
        ["led_status"],
        f"{DOMAIN}_numbers_{entry.data[CONF_HOST]}",
        SCAN_INTERVAL,
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as exc:
        _LOGGER.debug("Initial LED data fetch failed: %s", exc)

    async_add_entities([OpenwrtLedBrightnessNumber(coordinator, entry)], True)
    await coordinator.async_request_refresh()


class OpenwrtLedBrightnessNumber(CoordinatorEntity, NumberEntity):
    """Representation of the router LED brightness control."""

    _attr_has_entity_name = True
    _attr_name = "LED Brightness"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:led-on"

    def __init__(self, coordinator: SharedDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.entry = entry
        self._host = entry.data[CONF_HOST]
        self._attr_unique_id = f"{self._host}_led_brightness"
        self._optimistic_value: float | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the router."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._host)},
            name=f"OpenWrt Router ({self._host})",
            manufacturer="OpenWrt",
            model="Router",
        )

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return self.coordinator.last_update_success and self.coordinator.data.get("led_status") is not None

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        if self._optimistic_value is not None:
            return self._optimistic_value

        return self.coordinator.data.get("led_status")

    async def async_set_native_value(self, value: float) -> None:
        """Set the LED brightness percentage."""
        ubus = await self.coordinator.data_manager.get_ubus_connection_async()
        self._optimistic_value = round(value)
        self.async_write_ha_state()

        try:
            await ubus.set_led_brightness(value)
            self.coordinator.data_manager.invalidate_cache("led_status")
            await self.coordinator.async_request_refresh()
        finally:
            self._optimistic_value = None
