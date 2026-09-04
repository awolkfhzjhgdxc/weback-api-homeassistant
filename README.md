# WeBack Vacuum for Home Assistant

Custom component for Home Assistant providing support for robot vacuums using the WeBack / Grit Cloud ecosystem (Tesvor, WeBack, etc.).

## Features
- Full vacuum control (start, pause, stop, return to base, locate, fan speed / suction power control).
- Real-time cleaning map camera entity (`camera.<vacuum_name>_map`).
- Dynamic map path drawing with cleaned area and robot position tracking.
- Grit Cloud OAuth v2 authentication and WSS communication.
- UI Configuration via Config Flow.

## Installation

### Option 1: Automated Script
Run the included installer script:
```bash
./install.sh
```
Or specify the path to your Home Assistant config directory explicitly:
```bash
./install.sh /var/lib/homeassistant/homeassistant
# or
./install.sh /config
```

The script will:
- Auto-detect your Home Assistant directory (supports HA OS, Supervised, Container, and Core).
- Back up any existing `weback_vacuum` component.
- Copy files into `<config>/custom_components/weback_vacuum`.
- Advise the appropriate restart command.

### Option 2: Manual Installation
1. Copy the `custom_components/weback_vacuum` folder into your Home Assistant `<config>/custom_components/` directory.
2. Restart Home Assistant.
3. In Home Assistant, navigate to **Settings** -> **Devices & Services** -> **Add Integration**.
4. Search for **WeBack/Tesvor Vacuum** and enter your credentials.

## Requirements
- Home Assistant 2024.1+ (Python 3.12 / 3.13 / 3.14 compatible)
- `httpx`
- `websocket-client`
