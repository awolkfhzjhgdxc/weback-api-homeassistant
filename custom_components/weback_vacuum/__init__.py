"""Support for WeBack robot vacuums."""

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .webackapi import WebackApi
from .vacdevice import VacDevice
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["vacuum", "camera"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up WeBack from a config entry."""
    api = WebackApi(
        entry.data["username"],
        entry.data["password"],
        entry.data["region"],
        entry.data["language"],
        entry.data["application"],
        entry.data["client_id"],
        entry.data["api_version"],
    )
    if not await api.login():
        _LOGGER.error("WeBack login failed")
        return False

    robots = await api.get_robot_list()
    if not robots:
        _LOGGER.error("No robots found")
        return False

    devices = []
    for robot in robots:
        vac = VacDevice(
            robot["thing_name"],
            robot["thing_nickname"],
            robot["sub_type"],
            robot["thing_status"],
            entry.data["username"],
            entry.data["password"],
            entry.data["region"],
            entry.data["language"],
            entry.data["application"],
            entry.data["client_id"],
            entry.data["api_version"],
        )
        await vac.load_maps()
        devices.append(vac)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"api": api, "devices": devices}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
