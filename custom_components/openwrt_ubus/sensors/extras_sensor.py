"""Support for extra OpenWrt router sensors backed by ubus file helpers."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, UnitOfDataRate, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from ..shared_data_manager import SharedDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up extra sensors from a config entry."""
    data_manager_key = f"data_manager_{entry.entry_id}"
    data_manager = hass.data[DOMAIN][data_manager_key]

    coordinator = SharedDataUpdateCoordinator(
        hass,
        data_manager,
        ["vnstat_monthly", "speedtest_result"],
        f"{DOMAIN}_extras_{entry.data[CONF_HOST]}",
        SCAN_INTERVAL,
    )

    coordinator.known_vnstat_interfaces = set()

    async def _add_new_vnstat_entities() -> None:
        vnstat_data = coordinator.data.get("vnstat_monthly", {})
        if not isinstance(vnstat_data, dict):
            return

        new_interfaces = set(vnstat_data) - coordinator.known_vnstat_interfaces
        if not new_interfaces:
            return

        entity_registry = er.async_get(hass)
        new_entities = []

        for interface in sorted(new_interfaces):
            unique_id = f"{entry.data[CONF_HOST]}_vnstat_{interface}_monthly_traffic"
            if entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id):
                coordinator.known_vnstat_interfaces.add(interface)
                continue

            new_entities.append(OpenwrtVnstatMonthlySensor(coordinator, entry, interface))
            coordinator.known_vnstat_interfaces.add(interface)

        if new_entities:
            async_add_entities(new_entities, True)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as exc:
        _LOGGER.debug("Initial extras data fetch failed: %s", exc)

    entities = [OpenwrtSpeedtestSensor(coordinator, entry)]

    vnstat_data = coordinator.data.get("vnstat_monthly", {})
    if isinstance(vnstat_data, dict):
        for interface in sorted(vnstat_data):
            entities.append(OpenwrtVnstatMonthlySensor(coordinator, entry, interface))
            coordinator.known_vnstat_interfaces.add(interface)

    async_add_entities(entities, True)

    def _handle_coordinator_update() -> None:
        hass.async_create_task(_add_new_vnstat_entities())

    coordinator.async_add_listener(_handle_coordinator_update)


class OpenwrtExtraSensor(CoordinatorEntity, SensorEntity):
    """Base sensor for router extras."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SharedDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self._host = entry.data[CONF_HOST]

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the router."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._host)},
            name=f"OpenWrt Router ({self._host})",
            manufacturer="OpenWrt",
            model="Router",
        )


class OpenwrtSpeedtestSensor(OpenwrtExtraSensor):
    """Representation of the cached speedtest result."""

    _attr_name = "Speedtest"
    _attr_icon = "mdi:speedometer"
    _attr_device_class = SensorDeviceClass.DATA_RATE
    _attr_native_unit_of_measurement = UnitOfDataRate.MEGABITS_PER_SECOND
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: SharedDataUpdateCoordinator, entry: ConfigEntry) -> None:
        """Initialize the speedtest sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._host}_speedtest"

    @property
    def available(self) -> bool:
        """Return True if a speedtest result is currently available."""
        return self.coordinator.data.get("speedtest_result") is not None

    @property
    def native_value(self) -> float | None:
        """Return the current download speed."""
        data = self.coordinator.data.get("speedtest_result")
        if not isinstance(data, dict):
            return None

        return data.get("download_mbps")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra speedtest attributes."""
        data = self.coordinator.data.get("speedtest_result")
        if not isinstance(data, dict):
            return {}

        return {
            "upload_mbps": data.get("upload_mbps"),
            "download_mbps": data.get("download_mbps"),
            "ping": data.get("ping"),
            "jitter": data.get("jitter"),
            "packet_loss": data.get("packet_loss"),
            "timestamp": data.get("timestamp"),
            "isp": data.get("isp"),
            "interface": data.get("interface"),
        }


class OpenwrtVnstatMonthlySensor(OpenwrtExtraSensor):
    """Representation of per-interface monthly traffic from vnstat."""

    _attr_icon = "mdi:wan"
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.GIBIBYTES

    def __init__(
        self,
        coordinator: SharedDataUpdateCoordinator,
        entry: ConfigEntry,
        interface: str,
    ) -> None:
        """Initialize the vnstat sensor."""
        super().__init__(coordinator, entry)
        self.interface = interface
        self._attr_name = f"Monthly Traffic {interface}"
        self._attr_unique_id = f"{self._host}_vnstat_{interface}_monthly_traffic"

    @property
    def available(self) -> bool:
        """Return True if vnstat data for this interface is available."""
        return self.interface in self.coordinator.data.get("vnstat_monthly", {})

    @property
    def native_value(self) -> float | None:
        """Return the current monthly traffic total in GiB."""
        data = self.coordinator.data.get("vnstat_monthly", {}).get(self.interface)
        if not isinstance(data, dict):
            return None

        return data.get("total_gb")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return vnstat traffic details."""
        data = self.coordinator.data.get("vnstat_monthly", {}).get(self.interface)
        if not isinstance(data, dict):
            return {"interface": self.interface}

        return data
