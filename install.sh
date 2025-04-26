#!/bin/bash
set -e

echo "==== 安裝 PWM Fan Controller ===="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_TARGET="/usr/local/bin/pwm_fan_controller.py"
SERVICE_TARGET="/etc/systemd/system/pwmfan.service"
CONFIG_TARGET="/etc/pwmfan_config.json"

echo "[1/4] 安裝主程式..."
sudo install -m 755 "${SCRIPT_DIR}/src/pwm_fan_controller.py" "${BIN_TARGET}"

echo "[2/4] 安裝 systemd 服務..."
sudo install -m 644 "${SCRIPT_DIR}/systemd/pwmfan.service" "${SERVICE_TARGET}"

echo "[3/4] 安裝設定檔..."
if [ ! -f "${CONFIG_TARGET}" ]; then
    sudo install -m 644 "${SCRIPT_DIR}/pwmfan_config.json" "${CONFIG_TARGET}"
    echo "已建立新的設定檔: ${CONFIG_TARGET}"
else
    echo "偵測到已存在設定檔，保留現有版本: ${CONFIG_TARGET}"
fi

echo "[4/4] 啟用並啟動服務..."
sudo systemctl daemon-reload
sudo systemctl enable pwmfan.service
sudo systemctl restart pwmfan.service

echo "==== 安裝完成！ ===="
echo "版本資訊: $(cat ${SCRIPT_DIR}/VERSION)"
