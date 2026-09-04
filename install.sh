#!/usr/bin/env bash
set -e

# WeBack Vacuum - Home Assistant Auto Installer

GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
BLUE="\033[0;34m"
NC="\033[0m"

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_err() { echo -e "${RED}[ERROR]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_COMPONENT="${SCRIPT_DIR}/custom_components/weback_vacuum"

if [ ! -d "${SRC_COMPONENT}" ]; then
    log_err "Source component directory not found: ${SRC_COMPONENT}"
    exit 1
fi

TARGET_DIR=""

# 1. Check CLI argument
if [ -n "$1" ]; then
    TARGET_DIR="$1"
fi

# 2. Check environment variable
if [ -z "${TARGET_DIR}" ] && [ -n "${HA_CONFIG_DIR}" ]; then
    TARGET_DIR="${HA_CONFIG_DIR}"
fi

# 3. Auto-detect common Home Assistant configuration directories
if [ -z "${TARGET_DIR}" ]; then
    CANDIDATES=(
        "/config"
        "/var/lib/homeassistant/homeassistant"
        "${HOME}/.homeassistant"
        "/usr/share/hassio/homeassistant"
        "/var/lib/homeassistant"
    )
    for candidate in "${CANDIDATES[@]}"; do
        if [ -f "${candidate}/configuration.yaml" ] || [ -d "${candidate}/custom_components" ]; then
            TARGET_DIR="${candidate}"
            log_info "Auto-detected Home Assistant directory: ${TARGET_DIR}"
            break
        fi
    done
fi

# 4. Fallback: ask user if interactive
if [ -z "${TARGET_DIR}" ]; then
    if [ -t 0 ]; then
        echo -e "${YELLOW}Could not automatically detect Home Assistant configuration directory.${NC}"
        read -rp "Enter Home Assistant config path (e.g. /config or ~/.homeassistant): " user_input
        TARGET_DIR="${user_input/#\~/$HOME}"
    fi
fi

if [ -z "${TARGET_DIR}" ]; then
    log_err "Home Assistant configuration directory not specified."
    echo "Usage: $0 /path/to/homeassistant/config"
    exit 1
fi

if [ ! -d "${TARGET_DIR}" ]; then
    log_err "Target directory does not exist: ${TARGET_DIR}"
    exit 1
fi

DEST_CUSTOM_COMPONENTS="${TARGET_DIR}/custom_components"
DEST_COMPONENT="${DEST_CUSTOM_COMPONENTS}/weback_vacuum"

log_info "Installing WeBack Vacuum to ${DEST_COMPONENT}..."

mkdir -p "${DEST_CUSTOM_COMPONENTS}"

if [ -d "${DEST_COMPONENT}" ]; then
    log_warn "Existing installation found at ${DEST_COMPONENT}."
    BACKUP_DIR="${DEST_COMPONENT}.bak.$(date +%Y%m%d_%H%M%S)"
    log_info "Creating backup at ${BACKUP_DIR}..."
    cp -r "${DEST_COMPONENT}" "${BACKUP_DIR}"
fi

mkdir -p "${DEST_COMPONENT}"
cp -r "${SRC_COMPONENT}/." "${DEST_COMPONENT}/"

# Clean up pycache in destination if any
find "${DEST_COMPONENT}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

log_success "WeBack Vacuum successfully installed!"

# Attempt to detect restart mechanism
echo ""
log_info "To activate the integration, restart Home Assistant."

if command -v ha >/dev/null 2>&1; then
    log_info "Home Assistant CLI detected. You can restart with:"
    echo -e "  ${GREEN}ha core restart${NC}"
elif systemctl is-active --quiet homeassistant 2>/dev/null; then
    log_info "Systemd homeassistant service detected. You can restart with:"
    echo -e "  ${GREEN}systemctl restart homeassistant${NC}"
elif docker ps --format '{{.Names}}' 2>/dev/null | grep -qE '^homeassistant$'; then
    log_info "Docker homeassistant container detected. You can restart with:"
    echo -e "  ${GREEN}docker restart homeassistant${NC}"
else
    log_info "Restart Home Assistant from UI: Settings -> System -> Restart."
fi
