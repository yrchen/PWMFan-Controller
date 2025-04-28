[正體中文版本](README.md)

# PWM Fan Controller

A small daemon program that automatically adjusts the PWM fan speed based on CPU temperature, suitable for (but not limited to) Raspberry Pi devices.

## Testing Environment

This project has been tested and confirmed to run correctly on the following hardware and software environment:
* Raspberry Pi 4 Model B with [Argon POLY+ Raspberry Pi 4 Vented Case with PWM 30mm Fan](https://argon40.com/products/draft-argon-poly-raspberry-pi-4-vented-case-with-pwm-30mm-fan) on Raspberry Pi OS (bookworm)

## Prerequisites

Before installing and running this program, you need to ensure that the underlying hardware PWM functionality of the system has been enabled through system configuration. The program installation includes a setup service (`pwmfan-setup.service`) that attempts to export and enable the required PWM channel on each boot, but the underlying enablement steps still need to be performed manually.

### Enabling PWM on Raspberry Pi (Required Step)

1.  **Edit Configuration File:** Open the `/boot/config.txt` (or `/boot/firmware/config.txt` on newer systems) file:
    ```shell
    sudo nano /boot/firmware/config.txt
    # or sudo nano /boot/config.txt
    ```
2.  **Add dtoverlay:** Add one of the following lines at the end of the file, depending on the GPIO pin and PWM channel you are using:
    *   If using GPIO 12 (PWM0) or GPIO 18 (PWM0), add:
        ```
        dtoverlay=pwm
        ```
    *   If you need both GPIO 12/18 (PWM0) and GPIO 13/19 (PWM1), add:
        ```
        dtoverlay=pwm-2chan
        ```
    *   **Note:** This program defaults to using `pwm0` (configurable via `/etc/pwmfan_setup.ini`). Please select the correct pin and setting based on your hardware wiring.
3.  **Save and Reboot:** Save the file (Ctrl+O, Enter), exit (Ctrl+X), and then reboot the Raspberry Pi:
    ```shell
    sudo reboot
    ```
4.  **Verify (Optional):** After rebooting, check if the corresponding `pwmchipX` directory exists under `/sys/class/pwm/`. For example, if using `pwmchip0`, check if `/sys/class/pwm/pwmchip0/` exists.

### PWM Channel Export and Enablement (Handled Automatically by Setup Service)

After completing the `dtoverlay` step above and rebooting, the system should recognize the PWM hardware. The `pwmfan-setup.service` included in this project executes the `pwmfan_setup.sh` script at boot time. This script will:
1.  Read the `/etc/pwmfan_setup.ini` configuration file to get the PWM chip path and PWM number.
2.  Check if the corresponding PWM channel (e.g., `/sys/class/pwm/pwmchip0/pwm0`) has been exported. If not, it attempts to export it.
3.  Set the PWM period and initial duty cycle.
4.  Enable the PWM channel.

Therefore, under normal circumstances, you **do not** need to manually execute commands like `echo 0 > .../export` or `echo 1 > .../enable`.

## Installation

```shell
git clone https://github.com/yrchen/PWMFan-Controller.git
cd PWMFan-Controller
chmod +x install.sh
./install.sh
```

The installation script will install the main program, setup script, example configuration files, and two systemd service files into the system.

## Features
- Automatic temperature-controlled fan speed
- Support for manual real-time adjustments
- Support for automatic startup at boot via systemd
- Support for external configuration files
- Automatic handling of PWM channel export and initial setup

## System Services and Execution Flow

This project includes two systemd services:

1.  **`pwmfan-setup.service`**:
    *   Type: `oneshot` (executes a one-time task).
    *   Executes Script: `/usr/local/bin/pwmfan_setup.sh`.
    *   Purpose: During the boot process, ensures the PWM channel is exported, period/duty cycle are set, and it is enabled.
    *   Configuration File: Reads `/etc/pwmfan_setup.ini`.
2.  **`pwmfan.service`**:
    *   Type: `simple` (the main running daemon).
    *   Executes Script: `/usr/local/bin/pwm_fan_controller.py`.
    *   Purpose: Continuously monitors and adjusts the PWM fan speed based on CPU temperature.
    *   Configuration File: Reads `/etc/pwmfan_config.json`.
    *   **Dependencies:** This service is configured to start **after** `pwmfan-setup.service` has successfully executed (`After=` and `Requires=`), ensuring the PWM interface is ready.

**Execution Order:** Boot -> `pwmfan-setup.service` executes -> `pwmfan.service` executes.

## Configuration Files

This project uses two main configuration files:

1.  **`/etc/pwmfan_setup.ini`**:
    *   Purpose: Configures PWM hardware-related parameters, read by the `pwmfan_setup.sh` script.
    *   Content: Contains `PWMCHIP_PATH` (PWM controller path), `PWM_NUMBER` (PWM number used), `DEFAULT_PERIOD` (period), and `DEFAULT_DUTY_CYCLE` (initial duty cycle).
    *   If this file does not exist during installation, the example file from the project's `etc/` directory will be copied.
2.  **`/etc/pwmfan_config.json`**:
    *   Purpose: Configures the mapping between fan speed and CPU temperature (temperature control curve), read by the main program `pwm_fan_controller.py`.
    *   Format: JSON.
    *   If this file does not exist during installation, the example file from the project's `etc/` directory will be copied.

## Monitoring

*   **Check main service status:**
    ```shell
    sudo systemctl status pwmfan.service
    ```
*   **View real-time logs of the main service:**
    ```shell
    sudo journalctl -u pwmfan.service -f
    ```
*   **Check setup service status (usually will be inactive (dead) because it's oneshot):**
    ```shell
    sudo systemctl status pwmfan-setup.service
    ```
*   **View execution logs of the setup service (for debugging PWM initial setup issues):**
    ```shell
    sudo journalctl -u pwmfan-setup.service
    ```

## Localization

This project uses `gettext` for multi-language support. Translation files are located in the `locales/` directory.

### Translation Update Workflow

If new or modified strings requiring translation are added to the code, follow these steps to update the translation files. A `Makefile` is also provided in the project root to simplify some steps (requires `make` and `gettext` tools to be installed first).

1.  **Mark Strings:** In `src/pwm_fan_controller.py`, mark new strings using `_("String to translate")`.
2.  **Update POT Template:** Run the following command to rescan the source code and update the `.pot` template file:
    ```shell
    xgettext --language=Python --keyword=_ --output=locales/pwmfan_controller.pot src/pwm_fan_controller.py
    ```
    *(Makefile alternative: `make pot`)*

3.  **Merge PO Files:** Use `msgmerge` to merge changes from the `.pot` file into each language's `.po` file. Execute for each language:
    ```shell
    # Example: Merge English PO file
    msgmerge --update locales/en/LC_MESSAGES/pwmfan_controller.po locales/pwmfan_controller.pot
    # Example: Merge Traditional Chinese PO file
    msgmerge --update locales/zh_TW/LC_MESSAGES/pwmfan_controller.po locales/pwmfan_controller.pot
    ```
    *(Makefile alternative: `make update-po`, which automatically runs `make pot` first)*

4.  **Edit PO Files:** Open `locales/<language_code>/LC_MESSAGES/pwmfan_controller.po` (e.g., `locales/en/LC_MESSAGES/pwmfan_controller.po`), find the `msgstr ""` lines, and fill in the translation for the corresponding language. For strings marked with `#, fuzzy` added by `msgmerge`, check if the translation is still accurate and remove the `#, fuzzy` marker.
5.  **Compile MO Files:** Compile the translated `.po` files into binary `.mo` files used by the program. Execute for each language:
    ```shell
    # Example: Compile English MO file
    msgfmt locales/en/LC_MESSAGES/pwmfan_controller.po -o locales/en/LC_MESSAGES/pwmfan_controller.mo
    # Example: Compile Traditional Chinese MO file
    msgfmt locales/zh_TW/LC_MESSAGES/pwmfan_controller.po -o locales/zh_TW/LC_MESSAGES/pwmfan_controller.mo
    ```
    *(Makefile alternative: `make mo` or simply `make`. To update and compile in one step, run `make translate`)*

6.  **Reinstall:** Running the `install.sh` script will copy the updated `.mo` files to the system directory. If you prefer not to run the full installation again, you can manually copy the `.mo` files to `/usr/share/locale/<lang>/LC_MESSAGES/pwmfan_controller.mo`.

### Cleaning with Makefile

To delete all automatically generated translation files (`.pot` and `.mo`), you can run:
```shell
make clean
```
