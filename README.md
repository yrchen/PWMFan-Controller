# PWM Fan Controller

根據 CPU 溫度自動調整 PWM 風扇轉速的小型 daemon 程式，適用(但不限於) Raspberry Pi 裝置。

## 前置需求 (Prerequisites)

在安裝和執行此程式之前，您需要確保系統已啟用硬體 PWM 功能，並且對應的 sysfs 介面已匯出。

### 在 Raspberry Pi 上啟用 PWM

1.  **編輯設定檔:** 開啟 `/boot/config.txt` (或新版系統的 `/boot/firmware/config.txt`) 檔案：
    ```shell
    sudo nano /boot/firmware/config.txt
    # 或 sudo nano /boot/config.txt
    ```
2.  **新增 dtoverlay:** 在檔案末尾加入以下其中一行，具體取決於您使用的 GPIO 引腳和 PWM 通道：
    *   若使用 GPIO 12 (PWM0) 或 GPIO 18 (PWM0)，加入：
        ```
        dtoverlay=pwm
        ```
    *   若同時需要 GPIO 12/18 (PWM0) 和 GPIO 13/19 (PWM1)，加入：
        ```
        dtoverlay=pwm-2chan
        ```
    *   **注意:** 此程式預設使用 `pwm0`，通常對應 GPIO 12 或 GPIO 18。請根據您的硬體接線選擇正確的引腳和設定。
3.  **儲存並重啟:** 儲存檔案 (Ctrl+O, Enter) 並離開 (Ctrl+X)，然後重新啟動 Raspberry Pi：
    ```shell
    sudo reboot
    ```
4.  **驗證 (可選):** 重啟後，檢查 `/sys/class/pwm/pwmchip0/` 目錄是否存在。如果存在，並且裡面有 `export` 檔案，表示 PWM 介面已成功載入。

### 匯出 PWM 通道 (如果需要)

通常 `dtoverlay` 會自動匯出 PWM 通道。但如果 `/sys/class/pwm/pwmchip0/pwm0` 目錄不存在，您可能需要手動匯出：

```shell
echo 0 | sudo tee /sys/class/pwm/pwmchip0/export
```

確認 `/sys/class/pwm/pwmchip0/pwm0` 目錄出現後，您還需要確保它是啟用的：

```shell
echo 1 | sudo tee /sys/class/pwm/pwmchip0/pwm0/enable
```

**注意:** 此程式 (`pwm_fan_controller.py`) 預設會檢查 `pwm0` 是否存在且已啟用。

## 安裝

```shell
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
```shell
sudo systemctl status pwmfan.service
sudo journalctl -u pwmfan.service -f
```

## 多語系支援 (Localization)

本專案使用 `gettext` 實現多語系支援。翻譯檔案位於 `locales/` 目錄。

### 更新翻譯流程

若程式碼中有新增或修改需要翻譯的字串，請依照以下步驟更新翻譯檔案。專案根目錄也提供了一個 `Makefile`，可以簡化部分步驟 (需要先安裝 `make` 和 `gettext` 工具)。

1.  **標記字串:** 在 `src/pwm_fan_controller.py` 中，使用 `_("要翻譯的字串")` 將新字串標記出來。
2.  **更新 POT 模板:** 執行以下指令，重新掃描原始碼並更新 `.pot` 模板檔案：
    ```shell
    xgettext --language=Python --keyword=_ --output=locales/pwmfan_controller.pot src/pwm_fan_controller.py
    ```
    *(Makefile 替代指令: `make pot`)*

3.  **合併 PO 檔案:** 使用 `msgmerge` 將 `.pot` 的變更合併到各語言的 `.po` 檔案。針對每種語言執行：
    ```shell
    # 範例：合併英文 PO 檔
    msgmerge --update locales/en/LC_MESSAGES/pwmfan_controller.po locales/pwmfan_controller.pot
    # 範例：合併正體中文 PO 檔
    msgmerge --update locales/zh_TW/LC_MESSAGES/pwmfan_controller.po locales/pwmfan_controller.pot
    ```
    *(Makefile 替代指令: `make update-po`，此指令會自動先執行 `make pot`)*

4.  **編輯 PO 檔案:** 開啟 `locales/<語言代碼>/LC_MESSAGES/pwmfan_controller.po` (例如 `locales/en/LC_MESSAGES/pwmfan_controller.po`)，找到 `msgstr ""` 的地方填入對應語言的翻譯。對於由 `msgmerge` 新增的 `#, fuzzy` 標記的字串，請檢查翻譯是否仍然準確，並移除 `#, fuzzy` 標記。
5.  **編譯 MO 檔案:** 將翻譯完成的 `.po` 檔案編譯成程式使用的二進位 `.mo` 檔案。針對每種語言執行：
    ```shell
    # 範例：編譯英文 MO 檔
    msgfmt locales/en/LC_MESSAGES/pwmfan_controller.po -o locales/en/LC_MESSAGES/pwmfan_controller.mo
    # 範例：編譯正體中文 MO 檔
    msgfmt locales/zh_TW/LC_MESSAGES/pwmfan_controller.po -o locales/zh_TW/LC_MESSAGES/pwmfan_controller.mo
    ```
    *(Makefile 替代指令: `make mo` 或直接執行 `make`。若要一次完成更新與編譯，可執行 `make translate`)*

6.  **重新安裝:** 執行 `install.sh` 腳本會將更新後的 `.mo` 檔案複製到系統目錄。如果您不想重新執行完整安裝，也可以手動將 `.mo` 檔案複製到 `/usr/share/locale/<lang>/LC_MESSAGES/pwmfan_controller.mo`。

### 使用 Makefile 清理

若要刪除所有自動生成的翻譯檔案 (`.pot` 和 `.mo`)，可以執行：
```shell
make clean
```
