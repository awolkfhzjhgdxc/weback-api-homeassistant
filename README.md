# WeBack Vacuum for Home Assistant

Custom component for Home Assistant providing support for robot vacuums using the WeBack / Grit Cloud ecosystem (Tesvor, WeBack, Redmond, etc.).

[📖 Документация и настройка на русском языке (README_RU.md)](README_RU.md)

---

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

## Tested Devices
- **REDMOND RV-R670S** (LDS laser navigation, map generation, live tracking fully verified)
- Compatible with other WeBack / Grit Cloud based robots (Tesvor, Redmond, Mamibot, Neatsvor, etc.)

## Requirements
- Home Assistant 2024.1+ (Python 3.12 / 3.13 / 3.14 compatible)
- `httpx`
- `websocket-client`

## Credits & Acknowledgments
This project is based on and extends previous reverse engineering and integration work by the community:
- [opravdin/weback-unofficial](https://github.com/opravdin/weback-unofficial) — original WeBack cloud API protocol research and client.
- [Jezza34000/homeassistant_weback_component](https://github.com/Jezza34000/homeassistant_weback_component) — initial Home Assistant custom component foundation.

## License
Licensed under the [MIT License](LICENSE).


