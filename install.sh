#!/bin/bash
set -e

echo "==== Installing PWM Fan Controller ===="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_TARGET="/usr/local/bin/pwm_fan_controller.py"
SERVICE_TARGET="/etc/systemd/system/pwmfan.service"
CONFIG_TARGET="/etc/pwmfan_config.json"

echo "[1/4] Installing main script..."
sudo install -m 755 "${SCRIPT_DIR}/src/pwm_fan_controller.py" "${BIN_TARGET}"

echo "[2/4] Installing systemd service..."
sudo install -m 644 "${SCRIPT_DIR}/systemd/pwmfan.service" "${SERVICE_TARGET}"

echo "[3/4] Installing configuration file..."
if [ ! -f "${CONFIG_TARGET}" ]; then
    sudo install -m 644 "${SCRIPT_DIR}/pwmfan_config.json" "${CONFIG_TARGET}"
    echo "New configuration file created: ${CONFIG_TARGET}"
else
    echo "Existing configuration file detected, keeping current version: ${CONFIG_TARGET}"
fi

echo "[4/5] Installing localization files..."
LOCALE_BASE_TARGET="/usr/share/locale"
APP_NAME="pwmfan_controller"

for lang_dir in "${SCRIPT_DIR}/locales/"*; do
    if [ -d "${lang_dir}" ]; then
        lang=$(basename "${lang_dir}")
        target_dir="${LOCALE_BASE_TARGET}/${lang}/LC_MESSAGES"
        source_mo="${lang_dir}/LC_MESSAGES/${APP_NAME}.mo"

        if [ -f "${source_mo}" ]; then
            echo "Installing ${lang} translation to ${target_dir}..."
            sudo mkdir -p "${target_dir}"
            sudo install -m 644 "${source_mo}" "${target_dir}/${APP_NAME}.mo"
        else
            echo "Warning: ${source_mo} not found, skipping ${lang} translation installation."
        fi
    fi
done

echo "[5/5] Enabling and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable pwmfan.service
sudo systemctl restart pwmfan.service

echo "==== Installation complete! ===="
echo "Version info: $(cat ${SCRIPT_DIR}/VERSION)"
