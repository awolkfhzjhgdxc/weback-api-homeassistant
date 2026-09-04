"""
Weback API class
"""

import asyncio
import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timedelta

import httpx
import websocket
import ssl

from .vacmap import VacMap

_LOGGER = logging.getLogger(__name__)

# Socket
SOCK_CONNECTED = "Open"
SOCK_CLOSE = "Close"
SOCK_ERROR = "Error"
# API Answer
SUCCESS_OK = "success"
SERVICE_ERROR = "ServiceErrorException"
USER_NOT_EXIST = "UserNotExist"
PASSWORD_NOK = "PasswordInvalid"  # noqa: S105

# API
AUTH_URL = "https://user.grit-cloud.com/prod/oauth"
AUTH_URL_CHINA = "https://user.grit-cloud.cn/prod/oauth"
ROBOT_UPDATE = "thing_status_update"
MAP_DATA = "map_data"
N_RETRY = 8
ACK_TIMEOUT = 5
HTTP_TIMEOUT = 5


class WebackApi:
    """
    WeBack API
    Handle connection with OAuth server to get WSS credentials
    """

    def __init__(self, user, password, region, country, app, client_id, api_version):
        _LOGGER.debug("WebackApi __init__")

        # HTTP Oauth required param
        self.user = user
        self.password = password
        self.region = region
        self.app = app
        self.country = country
        self.client_id = client_id
        self.api_version = api_version

        # API auth & connection param
        self.jwt_token = None
        self.region_name = None
        self.wss_url = None
        self.api_url = None
        self.token_duration = 0
        self.token_exp = None

    async def login(self) -> bool:
        """ "
        Login to WebBack platform
        """
        params = {
            "json": {
                "payload": {
                    "opt": "login",
                    "pwd": hashlib.md5(
                        self.password.encode(),
                    ).hexdigest(),  # nosec B324
                },
                "header": {
                    "language": self.country,
                    "app_name": self.app,
                    "calling_code": "00" + self.region,
                    "api_version": self.api_version,
                    "account": self.user,
                    "client_id": self.client_id,
                },
            },
        }

        # Checking if the region is China to use the Chinese Auth URL
        if self.region == "86":
            auth_url_selected = AUTH_URL_CHINA
        else:
            auth_url_selected = AUTH_URL

        resp = await self.send_http(auth_url_selected, **params)

        if resp is None:
            _LOGGER.error(
                "WebackApi login failed, server sent an empty answer",
            )
            return False

        result_msg = resp.get("msg")

        if result_msg == SUCCESS_OK:
            # Login OK
            self.jwt_token = resp["data"]["jwt_token"]
            self.region_name = resp["data"]["region_name"]
            self.wss_url = resp["data"]["wss_url"]
            self.api_url = resp["data"]["api_url"]
            self.token_duration = resp["data"]["expired_time"] - 60

            # Calculate token expiration
            now_date = datetime.today()
            self.token_exp = now_date + timedelta(seconds=self.token_duration)
            _LOGGER.debug("WebackApi login successful")

            return True
        if result_msg == SERVICE_ERROR:
            # Wrong APP
            _LOGGER.error(
                "WebackApi login failed, application is not recognized",
            )
            return False
        if result_msg == USER_NOT_EXIST:
            # User NOK
            _LOGGER.error(
                "WebackApi login failed, user does not exist",
            )
            return False
        if result_msg == PASSWORD_NOK:
            # Password NOK
            _LOGGER.error("WebackApi login failed, wrong password")
            return False
        # Login NOK
        _LOGGER.error("WebackApi can't login (reason is: %s)", result_msg)
        return False

    @staticmethod
    def check_token_is_valid(token) -> bool:
        """
        Check if token validity is still OK or not
        """
        _LOGGER.debug("WebackApi checking token validity : %s", token)
        try:
            now_date = datetime.today() - timedelta(minutes=15)
            dt_token = datetime.strptime(str(token), "%Y-%m-%d %H:%M:%S.%f")
            if now_date < dt_token:
                _LOGGER.debug("WebackApi token is valid")
                return True
        except Exception as excpt_token:
            _LOGGER.debug("WebackApi failed to check token : %s", excpt_token)
        _LOGGER.debug("WebackApi token not valid")
        return False

    async def check_credentials(self) -> bool:
        """
        Check if credentials for HTTP link are OK
        """
        _LOGGER.debug("WebackApi (HTTP) Checking credentials...")
        if (
            not self.region_name
            or not self.jwt_token
            or not self.api_url
        ):
            _LOGGER.debug(
                "WebackApi (HTTP) Credentials invalid, renewing...",
            )
            return await self.login()
        return True

    async def get_robot_list(self):
        """
        Get robot things list registered from Weback server
        """
        _LOGGER.debug("WebackApi ask : robot list")
        if not await self.check_credentials():
            _LOGGER.error("WebackApi : credentials renewal failed")
            return None

        params = {
            "json": {"opt": "user_thing_list_get"},
            "headers": {"token": self.jwt_token, "region": self.region_name},
        }
        resp = await self.send_http(self.api_url, **params)

        if resp and resp.get("msg") == SUCCESS_OK:
            _LOGGER.debug(
                "WebackApi get robot list OK : %s",
                resp["data"]["thing_list"],
            )
            return resp["data"]["thing_list"]
        _LOGGER.error("WebackApi failed to get robot list (details : %s)", resp)
        return None

    async def get_reuse_map_by_id(self, map_id, sub_type, thing_name):
        """
        Get reuse map object by id
        """
        _LOGGER.debug("WebackApi ask : get reuse map = %s", map_id)
        if not await self.check_credentials():
            _LOGGER.error("WebackApi : credentials renewal failed")
            return []

        params = {
            "json": {
                "opt": "reuse_map_get",
                "map_id": str(map_id),
                "sub_type": sub_type,
                "thing_name": thing_name,
            },
            "headers": {"token": self.jwt_token, "region": self.region_name},
        }

        resp = await self.send_http(self.api_url, **params)

        if resp["msg"] == SUCCESS_OK:
            _LOGGER.debug("WebackApi get reuse map OK")
            return resp["data"]["map_data"]
        _LOGGER.error("WebackApi failed to get reuse map (details : %s)", resp)
        return []

    async def send_http(self, url, **params):
        """
        Send HTTP request.
        On a 401 response, renew credentials (re-login) and retry once
        so an expired JWT does not take the integration down.
        """
        _LOGGER.debug("Send HTTP request Url=%s Params=%s", url, params)
        timeout = httpx.Timeout(HTTP_TIMEOUT, connect=15.0)
        relogin_done = False

        for attempt in range(N_RETRY):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    req = await client.post(url, **params)
                    if req.status_code == 200:
                        # Server status OK
                        _LOGGER.debug("WebackApi : Send HTTP OK, return=200")
                        _LOGGER.debug("WebackApi : HTTP data received = %s", req.json())
                        return req.json()
                    if req.status_code == 401 and not relogin_done:
                        # Token expired or revoked -> renew credentials and
                        # retry immediately with the fresh token
                        _LOGGER.warning(
                            "WebackApi : 401 received, renewing credentials...",
                        )
                        relogin_done = True
                        if await self.login():
                            params["headers"] = {
                                "token": self.jwt_token,
                                "region": self.region_name,
                            }
                            continue
                        _LOGGER.error(
                            "WebackApi : re-login failed, giving up",
                        )
                        break
                    # Server status NOK
                    _LOGGER.warning(
                        "WebackApi : Bad server response (status code=%s) "
                        "retry... (%s/%s)",
                        req.status_code,
                        attempt,
                        N_RETRY,
                    )
            except httpx.RequestError as http_excpt:
                _LOGGER.debug(
                    "Send HTTP exception details=%s retry... (%s/%s)",
                    http_excpt,
                    attempt,
                    N_RETRY,
                )
        _LOGGER.error(
            "WebackApi : HTTP error after %s retry",
            N_RETRY,
        )
        return {"msg": "error", "details": f"Failed after {N_RETRY} retry"}


class WebackWssCtrl(WebackApi):
    """
    Weback WSS class
    """

    # Clean mode
    CLEAN_MODE_AUTO = "AutoClean"
    CLEAN_MODE_EDGE = "EdgeClean"
    CLEAN_MODE_EDGE_DETECT = "EdgeDetect"
    CLEAN_MODE_SPOT = "SpotClean"
    CLEAN_MODE_SINGLE_ROOM = "RoomClean"
    CLEAN_MODE_ROOMS = "SelectClean"
    CLEAN_MODE_MOP = "MopClean"
    CLEAN_MODE_SMART = "SmartClean"
    CLEAN_MODE_Z = "ZmodeClean"
    ROBOT_PLANNING_LOCATION = "PlanningLocation"
    ROBOT_PLANNING_RECT = "PlanningRect"

    # Other Working state
    RELOCATION = "Relocation"
    CHARGE_MODE_RETURNING = "BackCharging"
    DIRECTION_CONTROL = "DirectionControl"
    ROBOT_LOCATION_SOUND = "LocationAlarm"

    # Charging state
    CHARGE_MODE_CHARGING = "Charging"
    CHARGE_MODE_DOCK_CHARGING = "PileCharging"
    CHARGE_MODE_DIRECT_CHARGING = "DirCharging"
    CHARGE_MODE_CHARGE_DONE = "ChargeDone"

    # Idle state
    IDLE_MODE_HIBERNATING = "Hibernating"
    IDLE_MODE = "Idle"

    # Standby/Paused state
    CLEAN_MODE_STOP = "Pause"

    # Fan level
    FAN_DISABLED = "None"
    FAN_SPEED_QUIET = "Quiet"
    FAN_SPEED_NORMAL = "Normal"
    FAN_SPEED_HIGH = "Strong"
    FAN_SPEED_MAX = "Max"

    FAN_SPEEDS = {FAN_SPEED_QUIET, FAN_SPEED_NORMAL, FAN_SPEED_HIGH}

    # MOP Water level
    MOP_DISABLED = "None"
    MOP_SPEED_LOW = "Low"
    MOP_SPEED_NORMAL = "Default"
    MOP_SPEED_HIGH = "High"

    MOP_SPEEDS = {MOP_SPEED_LOW, MOP_SPEED_NORMAL, MOP_SPEED_HIGH}

    NO_FAN_NO_MOP = 0
    VACUUM_ON = 1
    MOP_ON = 2

    # Error state
    ROBOT_ERROR = "Malfunction"

    # Unknown state
    ROBOT_UNKNOWN = "unknown"

    # Robot Error codes
    ROBOT_ERROR_NO = "NoError"
    ROBOT_ERROR_UNKNOWN = "UnknownError"
    ROBOT_ERROR_LEFT_WHEEL = "LeftWheelWinded"
    ROBOT_ERROR_RIGHT_WHEEL = "RightWheelWinded"
    ROBOT_ERROR_WHEEL_WINDED = "WheelWinded"
    ROBOT_ERROR_60017 = "LeftWheelSuspend"
    ROBOT_ERROR_60019 = "RightWheelSuspend"
    ROBOT_ERROR_WHEEL_SUSPEND = "WheelSuspend"
    ROBOT_ERROR_LEFT_BRUSH = "LeftSideBrushWinded"
    ROBOT_ERROR_RIGHT_BRUSH = "RightSideBrushWinded"
    ROBOT_ERROR_SIDE_BRUSH = "SideBrushWinded"
    ROBOT_ERROR_60031 = "RollingBrushWinded"
    ROBOT_ERROR_COLLISION = "AbnormalCollisionSwitch"
    ROBOT_ERROR_GROUND = "AbnormalAntiFallingFunction"
    ROBOT_ERROR_FAN = "AbnormalFan"
    ROBOT_ERROR_DUSTBOX2 = "NoDustBox"
    ROBOT_ERROR_CHARGE_FOUND = "CannotFindCharger"
    ROBOT_ERROR_CHARGE_ERROR = "BatteryMalfunction"
    ROBOT_ERROR_LOWPOWER = "LowPower"
    ROBOT_ERROR_CHARGE = "BottomNotOpenedWhenCharging"
    ROBOT_ERROR_CAMERA_CONTACT_FAIL = "CameraContactFailure"
    ROBOT_ERROR_LIDAR_CONNECT_FAIL = "LidarConnectFailure"
    ROBOT_ERROR_TANK = "AbnormalTank"
    ROBOT_ERROR_SPEAKER = "AbnormalSpeaker"
    ROBOT_ERROR_NO_WATER_BOX = "NoWaterBox"
    ROBOT_ERROR_NO_WATER_MOP = "NoWaterMop"
    ROBOT_ERROR_WATER_BOX_EMPTY = "WaterBoxEmpty"
    ROBOT_ERROR_FLOATING = "WheelSuspendInMidair"
    ROBOT_ERROR_DUSTBOX = "DustBoxFull"
    ROBOT_ERROR_GUN_SHUA = "BrushTangled"
    ROBOT_ERROR_TRAPPED = "RobotTrapped"
    ROBOT_CHARGING_ERROR = "ChargingError"
    ROBOT_BOTTOM_NOT_OPENED_WHEN_CHARGING = "BottomNotOpenedWhenCharging"
    ROBOT_ERROR_60024 = "CodeDropped"
    ROBOT_ERROR_60026 = "NoDustBox"
    ROBOT_ERROR_60028 = "OperatingCurrentOverrun"
    ROBOT_ERROR_60029 = "VacuumMotorTangled"
    ROBOT_ERROR_60032 = "StuckWheels"
    ROBOT_ERROR_STUCK = "RobotStuck"
    ROBOT_ERROR_BE_TRAPPED = "RobotBeTrapped"
    ROBOT_ERROR_COVER_STUCK = "LaserHeadCoverStuck"
    ROBOT_ERROR_LASER_HEAD = "AbnormalLaserHead"
    ROBOT_ERROR_WALL_BLOCKED = "WallSensorBlocked"
    ROBOT_ERROR_VIR_WALL_FORB = "VirtualWallForbiddenZoneSettingError"

    CLEANING_STATES = {
        DIRECTION_CONTROL,
        ROBOT_PLANNING_RECT,
        RELOCATION,
        CLEAN_MODE_Z,
        CLEAN_MODE_AUTO,
        CLEAN_MODE_EDGE,
        CLEAN_MODE_EDGE_DETECT,
        CLEAN_MODE_SPOT,
        CLEAN_MODE_SINGLE_ROOM,
        CLEAN_MODE_ROOMS,
        CLEAN_MODE_MOP,
        CLEAN_MODE_SMART,
        CHARGE_MODE_RETURNING,
    }

    CHARGING_STATES = {
        CHARGE_MODE_CHARGING,
        CHARGE_MODE_DOCK_CHARGING,
        CHARGE_MODE_DIRECT_CHARGING,
    }

    DOCKED_STATES = {
        CHARGE_MODE_CHARGING,
        CHARGE_MODE_DOCK_CHARGING,
        CHARGE_MODE_DIRECT_CHARGING,
        CHARGE_MODE_CHARGE_DONE,
    }

    # Payload attributes
    ASK_STATUS = "working_status"
    SET_FAN_SPEED = "fan_status"
    GOTO_POINT = "goto_point"
    RECTANGLE_INFO = "virtual_rect_info"
    SPEAKER_VOLUME = "volume"
    SELECTED_ZONE = "selected_zone"
    PLANNING_RECT_POINT_NUM = "planning_rect_point_num"
    PLANNING_RECT_X = "planning_rect_x"
    PLANNING_RECT_Y = "planning_rect_y"
    ACTIVE_MAP_ID_PROP = "hismap_id"

    # Payload switches
    VOICE_SWITCH = "voice_switch"
    UNDISTURB_MODE = "undisturb_mode"
    SWITCH_VALUES = ["on", "off"]

    """
    WebSocket Weback API controller
    Handle websocket to send/receive robot control
    """

    def __init__(self, user, password, region, country, app, client_id, api_version):
        super().__init__(user, password, region, country, app, client_id, api_version)
        _LOGGER.debug("WebackApi WSS Control __init__")
        self.ws = None
        self.authorization = "Basic KG51bGwpOihudWxsKQ=="
        self.socket_state = SOCK_CLOSE
        self.robot_status = None
        self.subscriber = []
        self.wst = None
        self.ws = None
        self.map = None
        self._refresh_time = 60
        self._last_refresh = 0
        self.sent_counter = 0
        self._consecutive_poll_failures = 0
        self._available = True

    async def check_credentials(self):
        """
        Check if credentials for WSS link are OK
        """
        _LOGGER.debug("WebackApi (WSS) Checking credentials...")
        if (
            not self.region_name
            or not self.jwt_token
            or not self.check_token_is_valid(self.token_exp)
        ):
            _LOGGER.debug("WebackApi (WSS) Credentials need renewal")
            # Cred renewal necessary
            return bool(await self.login())
        _LOGGER.debug("WebackApi (WSS) Credentials are OK")
        return True

    async def open_wss_thread(self):
        """
        Connect WebSocket to Weback Server and create a thread to maintain connection alive
        """
        if not await self.check_credentials():
            _LOGGER.error("WebackApi (WSS) Failed to obtain WSS credentials")
            return False

        _LOGGER.debug(
            "WebackApi (WSS) Addr=%s / Region=%s / Token=%s",
            self.wss_url,
            self.region_name,
            self.jwt_token,
        )

        try:
            self.ws = websocket.WebSocketApp(
                self.wss_url,
                header={
                    "Authorization": self.authorization,
                    "region": self.region_name,
                    "token": self.jwt_token,
                    "Connection": "keep-alive, Upgrade",
                    "handshakeTimeout": "10000",
                },
                on_message=self.on_message,
                on_close=self.on_close,
                on_open=self.on_open,
                on_error=self.on_error,
                on_pong=self.on_pong,
            )

            self.wst = threading.Thread(target=self.ws.run_forever)
            self.wst.start()

            if self.wst.is_alive():
                _LOGGER.debug("WebackApi (WSS) Thread was init")
                return True
            else:
                _LOGGER.error("WebackApi (WSS) Thread connection init has FAILED")
                return False

        except Exception as e:
            self.socket_state = SOCK_ERROR
            _LOGGER.debug("WebackApi (WSS) Error while opening socket %s", e)
            return False

    async def connect_wss(self):
        _LOGGER.debug("WebackApi (WSS) Bypassed - WebSocket is permanently blocked by cloud WAF")
        return False

    def on_error(self, ws, error):
        """Socket "On_Error" event"""
        details = ""
        if error:
            details = f"(details : {error})"
        _LOGGER.debug("WebackApi (WSS) Error %s", details)
        self.socket_state = SOCK_ERROR

    def on_close(self, ws, close_status_code, close_msg):
        """Socket "On_Close" event"""
        _LOGGER.debug("WebackApi (WSS) Closed")

        if close_status_code or close_msg:
            _LOGGER.debug(
                "WebackApi (WSS) Close Status_code: %s ",
                str(close_status_code),
            )
            _LOGGER.debug("WebackApi (WSS) Close Message: %s", str(close_msg))
        self.socket_state = SOCK_CLOSE

    def on_pong(self, message):
        """Socket on_pong"""
        _LOGGER.debug("WebackApi (WSS) Got a Pong")

    def on_open(self, ws):
        """Socket "On_Open" event"""
        _LOGGER.debug("WebackApi (WSS) connection established OK")
        self.socket_state = SOCK_CONNECTED

    def on_message(self, ws, message):
        """Socket "On_Message" event"""
        self.sent_counter = 0
        wss_data = json.loads(message)
        _LOGGER.debug("WebackApi (WSS) Msg received %s", wss_data)
        if wss_data["notify_info"] == ROBOT_UPDATE:
            self.adapt_refresh_time(wss_data["thing_status"])

            if wss_data["thing_status"] != self.robot_status:
                _LOGGER.debug("New update from cloud ->> push update")
                self.robot_status = wss_data["thing_status"]
                self._call_subscriber()
            else:
                _LOGGER.debug("No update from cloud")
        elif wss_data["notify_info"] == MAP_DATA:
            _LOGGER.debug("WebackApi (WSS) Map data received")
            try:
                if not self.map:
                    self.map = VacMap(wss_data["map_data"])
                else:
                    self.map.wss_update(wss_data["map_data"])
            except Exception as msg_excpt:
                _LOGGER.error(
                    "WebackApi (WSS) Error during on_message (map_data) (details=%s)",
                    msg_excpt,
                )

            self.adapt_refresh_time(self.robot_status)
            self._call_subscriber()
        else:
            _LOGGER.error(
                "WebackApi (WSS) Received an unknown message from server : %s",
                wss_data,
            )

        # Close WSS link if we don't need it anymore
        # or it will get closed by remote side
        if self._refresh_time == 120:
            _LOGGER.debug("WebackApi (WSS) Closing WSS...")
            self.ws.close()
            self.socket_state = SOCK_CLOSE

    async def publish_wss(self, dict_message):
        """
        Publish payload over HTTP API (since WSS is blocked)
        """
        _LOGGER.debug("WebackApi (HTTP) Publishing message via API: %s", dict_message)
        if not await self.check_credentials():
            _LOGGER.error("WebackApi : credentials renewal failed")
            return False

        params = {
            "json": dict_message,
            "headers": {"token": self.jwt_token, "region": self.region_name},
        }
        
        resp = await self.send_http(self.api_url, **params)
        if resp and resp.get("msg") == "success":
            _LOGGER.debug("WebackApi (HTTP) Msg published OK via HTTP API")
            return True
        _LOGGER.error("WebackApi (HTTP) Failed to publish message via HTTP API: %s", resp)
        return False

    async def send_command(self, thing_name, sub_type, working_payload):
        """
        Pack command to send - restored original send_to_device format
        """
        _LOGGER.info(
            "WebackApi send_command payload=%s for robot=%s",
            working_payload,
            thing_name,
        )
        payload = {
            "topic_name": "$aws/things/" + thing_name + "/shadow/update",
            "opt": "send_to_device",
            "sub_type": sub_type,
            "topic_payload": {"state": working_payload},
            "thing_name": thing_name,
        }
        await self.check_credentials()
        published = await self.publish_wss(payload)
        if published:
            asyncio.create_task(self.force_cmd_refresh(thing_name, sub_type))
        return published

    async def force_cmd_refresh(self, thing_name, sub_type):
        """Force refresh after a command so the UI reflects it quickly"""
        _LOGGER.debug("WebackApi (HTTP) force refresh after sending cmd...")
        self._last_refresh = 0
        for attempt in range(8):
            await asyncio.sleep(0.5)
            try:
                robots = await self.get_robot_list()
                if not robots:
                    continue
                for r in robots:
                    if r.get("thing_name") == thing_name:
                        new_status = r.get("thing_status")
                        if new_status and new_status != self.robot_status:
                            _LOGGER.debug(
                                "Force refresh attempt %d status updated: %s",
                                attempt + 1,
                                new_status,
                            )
                            self.robot_status = new_status
                            self.adapt_refresh_time(new_status)
                            self._call_subscriber()
                            return
                        break
            except Exception as e:
                _LOGGER.warning("Error in force_cmd_refresh: %s", e)

    async def update_status(self, thing_name, sub_type):
        """
        Request to update robot status
        """
        _LOGGER.debug("WebackApi (WSS) update_status = %s", thing_name)
        payload = {
            "topic_name": "grit_tech/notify/server_2_device/" + thing_name,
            "opt": "sync_thing",
            "sub_type": sub_type,
            "topic_payload": {
                "notify_info": "sync_thing",
                "cmd_timestamp_s": int(time.time()),
            },
            "thing_name": thing_name,
        }
        await self.publish_wss(payload)

    def adapt_refresh_time(self, status):
        """Adapt refreshing time depending on robot status"""
        _LOGGER.debug("WebackApi (HTTP) adapt for : %s", status)
        if status.get("working_status", None) not in self.DOCKED_STATES:
            _LOGGER.debug("WebackApi (HTTP) > Set refreshing to 15s")
            self._refresh_time = 15
            return

        _LOGGER.debug("WebackApi (HTTP) > Set refreshing to 30s")
        self._refresh_time = 30

    async def refresh_handler(self, thing_name, sub_type):
        _LOGGER.info("WebackApi Start refresh_handler (HTTP polling mode)")
        self._refresh_time = 30
        while True:
            if time.time() - self._last_refresh >= self._refresh_time:
                try:
                    _LOGGER.debug("WebackApi (HTTP) Refreshing status...")
                    robots = await self.get_robot_list()
                    if robots is None:
                        self._consecutive_poll_failures += 1
                        if self._consecutive_poll_failures >= 3 and self._available:
                            _LOGGER.warning(
                                "WebackApi (HTTP) Cloud unreachable after %s polls, "
                                "marking robot unavailable",
                                self._consecutive_poll_failures,
                            )
                            self._available = False
                            self._call_subscriber()
                    else:
                        if self._consecutive_poll_failures:
                            _LOGGER.info(
                                "WebackApi (HTTP) Cloud reachable again after %s failures",
                                self._consecutive_poll_failures,
                            )
                        self._consecutive_poll_failures = 0
                        if not self._available:
                            self._available = True
                            self._call_subscriber()
                        for r in robots:
                            if r.get("thing_name") == thing_name:
                                new_status = r.get("thing_status")
                                if new_status and new_status != self.robot_status:
                                    _LOGGER.debug(
                                        "New status from HTTP polling -> push update: %s",
                                        new_status,
                                    )
                                    self.robot_status = new_status
                                    self.adapt_refresh_time(new_status)
                                    self._call_subscriber()
                                    self.on_status_updated()
                                break
                except Exception as refresh_excpt:
                    _LOGGER.exception(
                        "WebackApi (HTTP) Error during refresh_handler (details=%s)",
                        refresh_excpt,
                    )
                self._last_refresh = time.time()
            await asyncio.sleep(5)

    def on_status_updated(self):
        """Hook called after robot_status changed (overridden by VacDevice)"""

    def subscribe(self, subscriber):
        _LOGGER.debug("WebackApi: adding a new subscriber")
        self.subscriber.append(subscriber)

    def _call_subscriber(self):
        _LOGGER.debug("WebackApi: Calling subscriber (schedule_update_ha_state)")
        for subscriber in self.subscriber:
            subscriber(self)
