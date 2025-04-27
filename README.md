[English Version](README.en.md)

# PWM Fan Controller

根據 CPU 溫度自動調整 PWM 風扇轉速的小型 daemon 程式，適用(但不限於) Raspberry Pi 裝置。

## 測試環境

本專案已經在下列軟硬體環境測試可正常執行：
* Raspberry Pi 4 Model B 與 [Argon POLY+ Raspberry Pi 4 Vented Case with PWM 30mm Fan](https://argon40.com/products/draft-argon-poly-raspberry-pi-4-vented-case-with-pwm-30mm-fan) 於 Raspberry Pi OS (bookworm)

## 前置需求 (Prerequisites)

在安裝和執行此程式之前，您需要確保系統底層的硬體 PWM 功能已透過系統設定啟用。程式安裝時會包含一個設定服務 (`pwmfan-setup.service`)，它會嘗試在每次開機時匯出並啟用所需的 PWM 通道，但底層的啟用步驟仍需手動完成。

### 在 Raspberry Pi 上啟用 PWM (必要步驟)

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
    *   **注意:** 此程式預設使用 `pwm0` (可透過 `/etc/pwmfan_setup.ini` 設定)。請根據您的硬體接線選擇正確的引腳和設定。
3.  **儲存並重啟:** 儲存檔案 (Ctrl+O, Enter) 並離開 (Ctrl+X)，然後重新啟動 Raspberry Pi：
    ```shell
    sudo reboot
    ```
4.  **驗證 (可選):** 重啟後，檢查 `/sys/class/pwm/` 下對應的 `pwmchipX` 目錄是否存在。例如，如果使用 `pwmchip0`，應檢查 `/sys/class/pwm/pwmchip0/` 是否存在。

### PWM 通道匯出與啟用 (由 Setup Service 自動處理)

上述 `dtoverlay` 步驟完成並重啟後，系統應能辨識 PWM 硬體。本專案包含的 `pwmfan-setup.service` 會在開機時執行 `pwmfan_setup.sh` 腳本。此腳本會：
1.  讀取 `/etc/pwmfan_setup.ini` 設定檔以獲取 PWM chip 路徑和 PWM 編號。
2.  檢查對應的 PWM 通道 (例如 `/sys/class/pwm/pwmchip0/pwm0`) 是否已匯出。如果沒有，則嘗試匯出。
3.  設定 PWM 的週期 (period) 和初始工作週期 (duty cycle)。
4.  啟用 (enable) 該 PWM 通道。

因此，一般情況下您**不需要**再手動執行 `echo 0 > .../export` 或 `echo 1 > .../enable` 等指令。

## 安裝

```shell
git clone https://github.com/yrchen/PWMFan-Controller.git
cd PWMFan-Controller
chmod +x install.sh
./install.sh
```

安裝腳本會將主程式、設定腳本、範例設定檔以及兩個 systemd 服務檔安裝到系統中。

## 功能
- 自動溫控轉速
- 支援手動即時調整
- 支援 systemd 開機自動啟動
- 支援外部設定檔
- 自動處理 PWM 通道匯出與初始設定

## 系統服務與執行流程

本專案包含兩個 systemd 服務：

1.  **`pwmfan-setup.service`**:
    *   類型：`oneshot` (執行一次性任務)。
    *   執行腳本：`/usr/local/bin/pwmfan_setup.sh`。
    *   目的：在開機過程中，確保 PWM 通道已匯出、設定好週期/工作週期並已啟用。
    *   設定檔：讀取 `/etc/pwmfan_setup.ini`。
2.  **`pwmfan.service`**:
    *   類型：`simple` (主要執行的 daemon)。
    *   執行腳本：`/usr/local/bin/pwm_fan_controller.py`。
    *   目的：根據 CPU 溫度持續監控並調整 PWM 風扇轉速。
    *   設定檔：讀取 `/etc/pwmfan_config.json`。
    *   **依賴關係：** 此服務設定為在 `pwmfan-setup.service` 成功執行**之後**才會啟動 (`After=` 和 `Requires=`)，以確保 PWM 介面準備就緒。

**執行順序:** 開機 -> `pwmfan-setup.service` 執行 -> `pwmfan.service` 執行。

## 設定檔

本專案使用兩個主要的設定檔：

1.  **`/etc/pwmfan_setup.ini`**:
    *   用途：設定 PWM 硬體相關參數，供 `pwmfan_setup.sh` 腳本讀取。
    *   內容：包含 `PWMCHIP_PATH` (PWM 控制器路徑)、`PWM_NUMBER` (使用的 PWM 編號)、`DEFAULT_PERIOD` (週期) 和 `DEFAULT_DUTY_CYCLE` (初始工作週期)。
    *   安裝時若此檔案不存在，會從專案的 `etc/` 目錄複製範例檔案。
2.  **`/etc/pwmfan_config.json`**:
    *   用途：設定風扇轉速與 CPU 溫度的對應關係 (溫控曲線)，供主程式 `pwm_fan_controller.py` 讀取。
    *   格式：JSON。
    *   安裝時若此檔案不存在，會從專案的 `etc/` 目錄複製範例檔案。

## 監控

*   **檢查主服務狀態:**
    ```shell
    sudo systemctl status pwmfan.service
    ```
*   **查看主服務即時日誌:**
    ```shell
    sudo journalctl -u pwmfan.service -f
    ```
*   **檢查設定服務狀態 (通常會是 inactive (dead)，因為是 oneshot):**
    ```shell
    sudo systemctl status pwmfan-setup.service
    ```
*   **查看設定服務的執行日誌 (用於除錯 PWM 初始設定問題):**
    ```shell
    sudo journalctl -u pwmfan-setup.service
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
