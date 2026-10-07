"""Device registry helpers."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN


def via_device_kwargs(
    hass: HomeAssistant, identifier: str, config_entry_id: str | None = None
) -> dict[str, str]:
    """Return ``via_device_id`` kwargs for the device with the given identifier.

    ``via_device`` (an identifier tuple) is deprecated in favour of the parent's
    device id. Returns an empty dict when the parent is not registered yet,
    since an unknown id is rejected by the registry.
    """
    devices = dr.async_get(hass).async_get_devices(identifiers={(DOMAIN, identifier)})
    if not devices:
        return {}
    for device in devices:
        if device.config_entry_id == config_entry_id:
            return {"via_device_id": device.id}
    return {"via_device_id": devices[0].id}
