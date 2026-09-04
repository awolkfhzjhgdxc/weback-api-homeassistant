"""Support for Weback Vacuum Robots."""

import logging

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumEntityFeature,
)
from homeassistant.helpers.icon import icon_for_battery_level
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import DOMAIN, VacDevice

_LOGGER = logging.getLogger(__name__)

STATE_CLEANING = "cleaning"
STATE_DOCKED = "docked"
STATE_ERROR = "error"
STATE_IDLE = "idle"
STATE_PAUSED = "paused"
STATE_RETURNING = "returning"

STATE_MAPPING = {
    # STATE_CLEANING
    VacDevice.CLEAN_MODE_AUTO: STATE_CLEANING,
    VacDevice.CLEAN_MODE_EDGE: STATE_CLEANING,
    VacDevice.CLEAN_MODE_EDGE_DETECT: STATE_CLEANING,
    VacDevice.CLEAN_MODE_SPOT: STATE_CLEANING,
    VacDevice.CLEAN_MODE_SINGLE_ROOM: STATE_CLEANING,
    VacDevice.CLEAN_MODE_ROOMS: STATE_CLEANING,
    VacDevice.CLEAN_MODE_MOP: STATE_CLEANING,
    VacDevice.CLEAN_MODE_SMART: STATE_CLEANING,
    VacDevice.ROBOT_PLANNING_LOCATION: STATE_CLEANING,
    VacDevice.CLEAN_MODE_Z: STATE_CLEANING,
    VacDevice.DIRECTION_CONTROL: STATE_CLEANING,
    VacDevice.ROBOT_PLANNING_RECT: STATE_CLEANING,
    VacDevice.RELOCATION: STATE_CLEANING,
    # STATE_DOCKED
    VacDevice.CHARGE_MODE_CHARGING: STATE_DOCKED,
    VacDevice.CHARGE_MODE_DOCK_CHARGING: STATE_DOCKED,
    VacDevice.CHARGE_MODE_DIRECT_CHARGING: STATE_DOCKED,
    VacDevice.CHARGE_MODE_CHARGE_DONE: STATE_DOCKED,
    "Pilecharging": STATE_DOCKED,
    # STATE_PAUSED
    VacDevice.CLEAN_MODE_STOP: STATE_PAUSED,
    "Stop": STATE_PAUSED,
    "Standby": STATE_PAUSED,
    "Pause": STATE_PAUSED,
    "LocationAlarm": STATE_PAUSED,
    # STATE_IDLE
    VacDevice.IDLE_MODE: STATE_IDLE,
    VacDevice.IDLE_MODE_HIBERNATING: STATE_IDLE,
    "Cleandone": STATE_IDLE,
    "CleanDone": STATE_IDLE,
    # STATE_RETURNING
    VacDevice.CHARGE_MODE_RETURNING: STATE_RETURNING,
    "Backcharging": STATE_RETURNING,
    # STATE_ERROR
    VacDevice.ROBOT_ERROR: STATE_ERROR,
}

# Some models report time in minutes, not seconds
SUB_TYPES_REPORTING_MINUTES = ["x-styleb"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up the Weback robot vacuums."""
    devices = hass.data[DOMAIN][entry.entry_id]["devices"]
    vacuums = []
    for device in devices:
        vacuums.append(WebackVacuumRobot(device))
        hass.loop.create_task(device.watch_state())

    _LOGGER.debug("Adding Weback Vacuums to Home Assistant: %s", vacuums)
    async_add_entities(vacuums, False)


class WebackVacuumRobot(StateVacuumEntity):
    """Weback Vacuum"""

    def __init__(self, device: VacDevice):
        """Initialize the Weback Vacuum."""
        self.device = device
        self.device.subscribe(lambda vacdevice: self.schedule_update_ha_state(False))
        self._error = None

        self._attr_supported_features = (
            VacuumEntityFeature.TURN_ON
            | VacuumEntityFeature.TURN_OFF
            | VacuumEntityFeature.STATUS
            | VacuumEntityFeature.PAUSE
            | VacuumEntityFeature.STOP
            | VacuumEntityFeature.RETURN_HOME
            | VacuumEntityFeature.CLEAN_SPOT
            | VacuumEntityFeature.LOCATE
            | VacuumEntityFeature.START
            | VacuumEntityFeature.SEND_COMMAND
            | VacuumEntityFeature.FAN_SPEED
        )
        if hasattr(VacuumEntityFeature, "BATTERY"):
            self._attr_supported_features |= VacuumEntityFeature.BATTERY
        _LOGGER.info("Vacuum initialized: %s", self.name)

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def name(self):
        return self.device.nickname

    @property
    def available(self):
        _LOGGER.debug("Vacuum: available=%s", self.device.is_available)
        return self.device.is_available

    @property
    def state(self):
        try:
            state_mapping = STATE_MAPPING[self.device.current_mode]
            _LOGGER.debug("Vacuum: state(from mapping)=%s", state_mapping)
            return state_mapping
        except KeyError:
            _LOGGER.exception(
                "Found an unsupported state, state_code: %s",
                self.device.current_mode,
            )
            return None

    @property
    def battery_level(self):
        return self.device.battery_level

    @property
    def battery_icon(self):
        _LOGGER.debug(
            "Vacuum: battery_icon battery_level=%s, charging=%s",
            self.battery_level,
            self.is_charging,
        )
        return icon_for_battery_level(
            battery_level=self.battery_level,
            charging=self.is_charging,
        )

    @property
    def fan_speed(self):
        if self.device.vacuum_or_mop == 1:
            _LOGGER.debug("Vacuum: (vacuum mode) fan_speed=%s", self.device.fan_status)
            return self.device.fan_status
        if self.device.vacuum_or_mop == 2:
            _LOGGER.debug("Vacuum: (mop mode) fan_speed=%s", self.device.mop_status)
            return self.device.mop_status
        _LOGGER.debug("Vacuum: no Fan / no Mop")
        return None

    @property
    def fan_speed_list(self):
        if self.device.vacuum_or_mop == 1:
            _LOGGER.debug(
                "Vacuum: (vacuum mode) fan_speed_list=%s",
                self.device.fan_speed_list,
            )
            return self.device.fan_speed_list
        if self.device.vacuum_or_mop == 2:
            _LOGGER.debug(
                "Vacuum: (mop mode) fan_speed_list=%s",
                self.device.mop_level_list,
            )
            return self.device.mop_level_list
        _LOGGER.debug("Vacuum: no Fan / no Mop fan_speed_list=None")
        return None

    @property
    def error(self):
        _LOGGER.debug("Vacuum: error=%s", self.device.error_info)
        return self.device.error_info

    @property
    def unique_id(self) -> str:
        return self.device.name

    @property
    def is_on(self):
        _LOGGER.debug("Vacuum: is_on=%s", self.device.is_cleaning)
        return self.device.is_cleaning

    @property
    def is_charging(self):
        return self.device.is_charging

    @property
    def extra_state_attributes(self) -> dict:
        mode = "vacuum" if self.device.vacuum_or_mop == 1 else "mop"
        extra_value = {
            "robot_mode": mode,
            "error_info": self.device.error_info,
        }

        if "volume" in self.device.robot_status:
            extra_value["volume"] = self.device.robot_status["volume"]
        if "voice" in self.device.robot_status:
            extra_value["voice"] = self.device.robot_status["voice"]
        if "undisturb_mode" in self.device.robot_status:
            extra_value["undisturb_mode"] = self.device.robot_status["undisturb_mode"]
        if "clean_area" in self.device.robot_status:
            clean_area = self.device.robot_status["clean_area"]
            if clean_area is None:
                clean_area = 0
            extra_value["clean_area"] = round(clean_area, 1)
        if "clean_time" in self.device.robot_status:
            clean_time = self.device.robot_status["clean_time"]
            if clean_time is None:
                clean_time = 0
            if self.device.sub_type in SUB_TYPES_REPORTING_MINUTES:
                extra_value["clean_time"] = clean_time
            else:
                extra_value["clean_time"] = round(clean_time / 60, 0)
        return extra_value

    def on_error(self, error):
        if error == self.device.ROBOT_ERROR_NO:
            self._error = None
        else:
            self._error = error
        _LOGGER.debug("Vacuum: on_error=%s", self._error)
        self.hass.bus.fire(
            "weback_vacuum",
            {"entity_id": self.entity_id, "error": error},
        )
        self.schedule_update_ha_state(False)

    async def async_turn_on(self, **kwargs):
        _LOGGER.debug("Vacuum: turn_on")
        await self.device.turn_on()
        self.device.robot_status["working_status"] = VacDevice.CLEAN_MODE_AUTO
        self.async_write_ha_state()

    async def async_start(self, **kwargs):
        _LOGGER.debug("Vacuum: async_start")
        await self.device.turn_on()
        self.device.robot_status["working_status"] = VacDevice.CLEAN_MODE_AUTO
        self.async_write_ha_state()

    async def async_stop(self, **kwargs):
        _LOGGER.debug("Vacuum: async_stop called")
        await self.device.pause()
        self.device.robot_status["working_status"] = VacDevice.CLEAN_MODE_STOP
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        _LOGGER.debug("Vacuum: async_turn_off")
        await self.device.return_to_base()
        self.device.robot_status["working_status"] = VacDevice.CHARGE_MODE_RETURNING
        self.async_write_ha_state()

    async def async_return_to_base(self, **kwargs):
        _LOGGER.debug("Vacuum: return_to_base")
        await self.device.return_to_base()
        self.device.robot_status["working_status"] = VacDevice.CHARGE_MODE_RETURNING
        self.async_write_ha_state()

    async def async_pause(self):
        _LOGGER.debug("Vacuum: async_pause called")
        await self.device.pause()
        self.device.robot_status["working_status"] = VacDevice.CLEAN_MODE_STOP
        self.async_write_ha_state()

    async def async_locate(self, **kwargs) -> None:
        _LOGGER.debug("Vacuum: locate")
        await self.device.locate()
        self.device.robot_status["working_status"] = "VoiceLocation"
        self.async_write_ha_state()

    async def async_set_fan_speed(self, fan_speed, **kwargs):
        _LOGGER.debug("Vacuum: set_fan_speed (speed=%s)", fan_speed)
        await self.device.set_fan_water_speed(fan_speed)

    async def async_clean_spot(self, **kwargs):
        _LOGGER.debug("Vacuum: clean_spot")
        await self.device.clean_spot()
        self.device.robot_status["working_status"] = VacDevice.CLEAN_MODE_SPOT
        self.async_write_ha_state()

    async def async_goto_location(self, point: str):
        _LOGGER.debug("Vacuum: goto_location (point=%s)", point)
        await self.device.goto(point)

    async def async_clean_rectangle(self, rectangle: str):
        _LOGGER.debug("Vacuum: clean_rectangle (rectangle=%s)", rectangle)
        await self.device.clean_rect(rectangle)

    async def async_send_command(self, command, params=None, **kwargs):
        _LOGGER.debug(
            "Vacuum: send_command (command=%s / params=%s / kwargs=%s)",
            command,
            params,
            kwargs,
        )
        if command == "app_segment_clean":
            await self.device.clean_room(params)
        elif command == "app_zoned_clean":
            await self.device.clean_zone(params)
        elif command == "app_goto_target":
            await self.device.goto([int(params[0] / 10), int(params[1] / 10)])
        else:
            await self.device.send_command(
                self.device.name,
                self.device.sub_type,
                params,
            )
