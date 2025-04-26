#!/bin/bash
set -e

echo "==== Installing PWM Fan Controller ===="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Fan Controller specific paths
FC_BIN_TARGET="/usr/local/bin/pwmfan_controller.py"
FC_SERVICE_TARGET="/etc/systemd/system/pwmfan-controller.service"
FC_CONFIG_TARGET="/etc/pwmfan_config.json"

# PWM Setup specific paths
PWM_SETUP_BIN_TARGET="/usr/local/bin/pwmfan_setup.sh"
PWM_SETUP_SERVICE_TARGET="/etc/systemd/system/pwmfan-setup.service"
# PWM_SETUP_CONFIG_DIR="/etc/pwm_controller" # Directory no longer needed if config is directly in /etc
PWM_SETUP_CONFIG_FILE="/etc/pwmfan_setup.ini"


echo "[1/6] Installing PWM setup script..."
sudo install -m 755 "${SCRIPT_DIR}/src/pwmfan_setup.sh" "${PWM_SETUP_BIN_TARGET}"

echo "[2/6] Installing PWM setup systemd service..."
sudo install -m 644 "${SCRIPT_DIR}/etc/systemd/pwmfan-setup.service" "${PWM_SETUP_SERVICE_TARGET}"

echo "[3/6] Installing main fan controller script..."
sudo install -m 755 "${SCRIPT_DIR}/src/pwmfan_controller.py" "${FC_BIN_TARGET}"

echo "[4/6] Installing fan controller systemd service..."
sudo install -m 644 "${SCRIPT_DIR}/etc/systemd/pwmfan-controller.service" "${FC_SERVICE_TARGET}"

echo "[5/6] Installing fan controller configuration file..."
if [ ! -f "${FC_CONFIG_TARGET}" ]; then
    sudo install -m 644 "${SCRIPT_DIR}/etc/pwmfan_config.json" "${FC_CONFIG_TARGET}"
    echo "New fan controller configuration file created: ${FC_CONFIG_TARGET}"
else
    echo "Existing fan controller configuration file detected, keeping current version: ${FC_CONFIG_TARGET}"
fi

echo "[+] Installing PWM setup configuration file (if needed)..."
if [ ! -f "${PWM_SETUP_CONFIG_FILE}" ]; then
    sudo install -m 644 "${SCRIPT_DIR}/etc/pwmfan_setup.ini" "${PWM_SETUP_CONFIG_FILE}"
    echo "New PWM setup configuration file created: ${PWM_SETUP_CONFIG_FILE}"
else
    echo "Existing PWM setup configuration file detected, keeping current version: ${PWM_SETUP_CONFIG_FILE}"
fi

echo "[6/7] Installing localization files..."
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

echo "[7/7] Enabling and starting services..."
sudo systemctl daemon-reload
# Enable both services. pwm-setup is oneshot, so --now isn't needed here.
sudo systemctl enable pwmfan-setup.service
# Enable and restart the main fan controller service
sudo systemctl enable --now pwmfan-controller.service
# Explicitly run pwm-setup once after install/update in case it needs to run before first restart
echo "Running initial PWM setup..."
sudo systemctl start pwmfan-setup.service


echo "==== Installation complete! ===="
echo "Version info: $(cat ${SCRIPT_DIR}/VERSION)"
