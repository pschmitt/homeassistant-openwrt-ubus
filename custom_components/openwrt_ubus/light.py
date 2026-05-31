"""Support for dynamic OpenWrt LED light entities."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import re
from typing import Any

from homeassistant.components.light import ATTR_EFFECT, ColorMode, LightEntity, LightEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .shared_data_manager import SharedDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)
LED_NAME_PREFIX_RE = re.compile(r"^(rgb:)")
TRIGGER_LABELS = {
    "none": "Manual",
    "default-on": "Always On",
    "disk-activity": "Disk Activity",
    "disk-read": "Disk Read",
    "disk-write": "Disk Write",
    "heartbeat": "Heartbeat",
    "netdev": "Network Activity",
    "timer": "Timer",
    "usbport": "USB Port",
    "mmc0": "MMC0",
    "omnia-mcu": "Omnia MCU",
}


def _friendly_led_name(name: str) -> str:
    """Convert a kernel LED name into a cleaner entity name."""
    cleaned = LED_NAME_PREFIX_RE.sub("", name).strip(":")
    if cleaned.lower().startswith("wlan-"):
        suffix = cleaned.split("-", 1)[1]
        return f"WLAN {suffix}"
    if cleaned.lower().startswith("lan-"):
        suffix = cleaned.split("-", 1)[1]
        return f"LAN {suffix}"
    if cleaned == "mmc0":
        return "MMC0"
    return cleaned.replace("-", " ").replace(":", " ").title()


def _friendly_trigger_name(trigger: str) -> str:
    """Convert a trigger token into a user-facing label."""
    if trigger in TRIGGER_LABELS:
        return TRIGGER_LABELS[trigger]

    if trigger.endswith(":link"):
        return f"{trigger.rsplit(':', 1)[0]} Link"
    if trigger.endswith(":1Gbps"):
        return f"{trigger.rsplit(':', 1)[0]} 1 Gbps"
    if trigger.endswith(":100Mbps"):
        return f"{trigger.rsplit(':', 1)[0]} 100 Mbps"
    if trigger.endswith(":10Mbps"):
        return f"{trigger.rsplit(':', 1)[0]} 10 Mbps"

    return trigger


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up per-LED light entities from a config entry."""
    data_manager_key = f"data_manager_{entry.entry_id}"
    data_manager = hass.data[DOMAIN][data_manager_key]

    coordinator = SharedDataUpdateCoordinator(
        hass,
        data_manager,
        ["leds"],
        f"{DOMAIN}_lights_{entry.data[CONF_HOST]}",
        SCAN_INTERVAL,
    )
    coordinator.known_leds = set()

    async def _add_new_led_entities() -> None:
        led_data = coordinator.data.get("leds", {})
        if not isinstance(led_data, dict):
            return

        new_leds = set(led_data) - coordinator.known_leds
        if not new_leds:
            return

        entity_registry = er.async_get(hass)
        new_entities = []

        for led_name in sorted(new_leds):
            unique_id = f"{entry.data[CONF_HOST]}_led_{led_name}"
            if entity_registry.async_get_entity_id("light", DOMAIN, unique_id):
                coordinator.known_leds.add(led_name)
                continue

            new_entities.append(OpenwrtLedLight(coordinator, entry, led_name))
            coordinator.known_leds.add(led_name)

        if new_entities:
            async_add_entities(new_entities, True)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as exc:
        _LOGGER.debug("Initial LED data fetch failed: %s", exc)

    entities = []
    led_data = coordinator.data.get("leds", {})
    if isinstance(led_data, dict):
        for led_name in sorted(led_data):
            entities.append(OpenwrtLedLight(coordinator, entry, led_name))
            coordinator.known_leds.add(led_name)

    if entities:
        async_add_entities(entities, True)

    def _handle_coordinator_update() -> None:
        hass.async_create_task(_add_new_led_entities())

    coordinator.async_add_listener(_handle_coordinator_update)


class OpenwrtLedLight(CoordinatorEntity, LightEntity):
    """Representation of a single OpenWrt LED."""

    _attr_has_entity_name = True
    _attr_entity_registry_visible_default = False

    def __init__(self, coordinator: SharedDataUpdateCoordinator, entry: ConfigEntry, led_name: str) -> None:
        """Initialize the light."""
        super().__init__(coordinator)
        self.entry = entry
        self.led_name = led_name
        self._host = entry.data[CONF_HOST]
        self._attr_name = _friendly_led_name(led_name)
        self._attr_unique_id = f"{self._host}_led_{led_name}"
        self._last_non_manual_trigger: str | None = None
        self._optimistic_is_on: bool | None = None
        self._optimistic_trigger: str | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Track the last active non-manual trigger."""
        led = self._led
        if led is not None and led.get("current_trigger") not in (None, "none"):
            self._last_non_manual_trigger = led.get("current_trigger")
        self._optimistic_is_on = None
        self._optimistic_trigger = None
        super()._handle_coordinator_update()

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
    def _led(self) -> dict[str, Any] | None:
        """Return the current LED data for this entity."""
        led_data = self.coordinator.data.get("leds", {})
        if not isinstance(led_data, dict):
            return None
        led = led_data.get(self.led_name)
        return led if isinstance(led, dict) else None

    @property
    def available(self) -> bool:
        """Return True if LED data is available."""
        return self._led is not None

    @property
    def _current_trigger(self) -> str | None:
        """Return the current trigger, preferring optimistic state."""
        if self._optimistic_trigger is not None:
            return self._optimistic_trigger
        led = self._led
        if led is None:
            return None
        return led.get("current_trigger")

    @property
    def is_on(self) -> bool | None:
        """Return whether the LED is on."""
        if self._optimistic_is_on is not None:
            return self._optimistic_is_on
        led = self._led
        if led is None:
            return None
        return bool(led.get("is_on"))

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        """Return the supported color modes for this LED."""
        return {ColorMode.ONOFF}

    @property
    def color_mode(self) -> ColorMode | None:
        """Return the active color mode for this LED."""
        return ColorMode.ONOFF if self.is_on else None

    @property
    def supported_features(self) -> LightEntityFeature:
        """Return supported optional features."""
        led = self._led or {}
        if led.get("supports_effects"):
            return LightEntityFeature.EFFECT
        return LightEntityFeature(0)

    @property
    def effect_list(self) -> list[str] | None:
        """Return the available trigger modes as light effects."""
        led = self._led
        if led is None or not led.get("supports_effects"):
            return None
        return [_friendly_trigger_name(trigger) for trigger in led.get("triggers", [])]

    @property
    def effect(self) -> str | None:
        """Return the current trigger mode."""
        trigger = self._current_trigger
        if trigger in (None, "none"):
            return None
        return _friendly_trigger_name(trigger)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra LED attributes."""
        led = self._led
        if led is None:
            return {}
        return {
            "led_name": self.led_name,
            "led_section": led.get("section"),
            "current_trigger": self._current_trigger,
            "configured_trigger": led.get("configured_trigger"),
            "configured_default": led.get("configured_default"),
            "available_triggers": led.get("triggers"),
            "current_brightness": led.get("brightness"),
            "max_brightness": led.get("max_brightness"),
        }

    def _label_to_trigger(self, label: str | None) -> str | None:
        """Resolve a friendly effect label back to its raw trigger token."""
        if label is None:
            return None
        for trigger in (self._led or {}).get("triggers", []):
            if _friendly_trigger_name(trigger) == label:
                return trigger
        return None

    async def _refresh_after_change(self) -> None:
        """Refresh LED state after the router applies the UCI change."""
        self.coordinator.data_manager.invalidate_cache("leds")
        await asyncio.sleep(2)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the LED on or change its mode."""
        led = self._led
        if led is None:
            return

        ubus = await self.coordinator.data_manager.get_ubus_connection_async()
        target_trigger = self._label_to_trigger(kwargs.get(ATTR_EFFECT))
        if target_trigger is None and led.get("current_trigger") != "none":
            target_trigger = led.get("current_trigger")
        if target_trigger is None:
            target_trigger = self._last_non_manual_trigger or "none"

        if target_trigger != "none":
            self._last_non_manual_trigger = target_trigger

        await ubus.configure_led(led["section"], target_trigger, True)
        self._optimistic_is_on = True
        self._optimistic_trigger = target_trigger
        self.async_write_ha_state()
        await self._refresh_after_change()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the LED off."""
        led = self._led
        if led is None:
            return

        ubus = await self.coordinator.data_manager.get_ubus_connection_async()
        if led.get("current_trigger") not in (None, "none"):
            self._last_non_manual_trigger = led.get("current_trigger")

        await ubus.configure_led(led["section"], "none", False)
        self._optimistic_is_on = False
        self._optimistic_trigger = "none"
        self.async_write_ha_state()
        await self._refresh_after_change()
