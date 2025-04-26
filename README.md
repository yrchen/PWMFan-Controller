# PWM Fan Controller

根據 CPU 溫度自動調整 PWM 風扇轉速的小型 daemon 程式，適用(但不限於) Raspberry Pi 裝置。

## 安裝

```bash
git clone https://github.com/yrchen/PWMFan-Controller.git
cd PWMFan-Controller
chmod +x install.sh
./install.sh
```

## 功能
- 自動溫控轉速
- 支援手動即時調整
- 支援 systemd 開機自動啟動
- 支援外部設定檔

## 設定檔

編輯 `/etc/pwmfan_config.json` 自訂溫控曲線。

## 監控
```bash
sudo systemctl status pwmfan.service
sudo journalctl -u pwmfan.service -f
```
