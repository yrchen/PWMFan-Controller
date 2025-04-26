#!/usr/bin/env python3
import argparse
import gettext
import json
import locale
import logging
import os
import signal
import time

# Setup localization
APP_NAME = "pwmfan_controller"
# Assume locales dir is one level up from src/, adjust if needed for installation
# LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'locales') # Remove hardcoded path

try:
    # Try to set locale from environment
    locale.setlocale(locale.LC_ALL, '')
    lang_code, encoding = locale.getlocale()
    if lang_code:
        # Use detected language, let gettext find the standard locale dir
        lang = gettext.translation(APP_NAME, languages=[lang_code], fallback=True)
    else:
        # Fallback to English if no locale detected, let gettext find the standard locale dir
        lang = gettext.translation(APP_NAME, languages=['en'], fallback=True)
except (locale.Error, FileNotFoundError, TypeError):
    # Fallback to NullTranslations if locale setting fails, file not found, or lang_code is None
    lang = gettext.NullTranslations()

_ = lang.gettext # Assign the translation function

# PWM sysfs path
PWM_CHIP_PATH = "/sys/class/pwm/pwmchip0"
PWM_PATH = os.path.join(PWM_CHIP_PATH, "pwm0")

# CPU temperature sensor path
TEMP_SENSOR_PATH = "/sys/class/thermal/thermal_zone0/temp"

# Configuration file path
CONFIG_FILE = "/etc/pwmfan_config.json"

# Built-in default curve
DEFAULT_CURVE = [
    {"temp": 40, "duty": 20},
    {"temp": 50, "duty": 40},
    {"temp": 60, "duty": 70},
    {"temp": 70, "duty": 100},
]

# Read PWM period
def read_period():
    with open(os.path.join(PWM_PATH, "period"), "r") as f:
        return int(f.read().strip())

# Set duty cycle (percentage)
def set_duty_cycle(percent, period):
    percent = max(0, min(100, percent))
    duty_ns = int(period * (percent / 100.0))
    with open(os.path.join(PWM_PATH, "duty_cycle"), "w") as f:
        f.write(str(duty_ns))

# Read CPU temperature (°C)
def read_temperature():
    with open(TEMP_SENSOR_PATH, "r") as f:
        temp_milli = int(f.read().strip())
        return temp_milli / 1000.0

# Load configuration file
def load_curve_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            curve = data.get("temperature_to_duty", [])
            if not curve:
                # Use _() for translatable strings
                logging.warning(_("Configuration file missing 'temperature_to_duty', using default curve"))
                return DEFAULT_CURVE
            curve.sort(key=lambda x: x["temp"])
            # Use _() and .format() for strings with variables
            logging.info(_("Successfully loaded configuration file: {config_file}").format(config_file=CONFIG_FILE))
            return curve
    except Exception as e:
        logging.warning(_("Failed to load configuration file: {error}, using default curve").format(error=e))
        return DEFAULT_CURVE

# Return duty cycle based on temperature
def temp_to_duty(temp_celsius, curve):
    for rule in curve:
        if temp_celsius < rule["temp"]:
            return rule["duty"]
    return curve[-1]["duty"]

def check_pwm_enabled():
    try:
        with open(os.path.join(PWM_PATH, "enable"), "r") as f:
            enabled = int(f.read().strip())
            if enabled != 1:
                # Use _() for translatable strings
                raise RuntimeError(_("PWM is not enabled (enable file is not 1)"))
    except Exception as e:
        # Use _() and .format() for strings with variables
        logging.error(_("Failed to check PWM status: {error}").format(error=e))
        exit(1)

def auto_mode(period, interval, verbose):
    last_config_mtime = 0
    curve = DEFAULT_CURVE
    last_duty = -1

    # Use _() for translatable strings
    logging.info(_("Starting Auto Mode"))

    while True:
        try:
            # Check for configuration file updates
            if os.path.exists(CONFIG_FILE):
                mtime = os.path.getmtime(CONFIG_FILE)
                if mtime != last_config_mtime:
                    curve = load_curve_config()
                    last_config_mtime = mtime

            temp = read_temperature()
            duty = temp_to_duty(temp, curve)

            if verbose:
                # Use _() and .format() for strings with variables
                logging.info(_("Temperature: {temp:.1f}°C => Setting duty cycle to {duty}%").format(temp=temp, duty=duty))

            if duty != last_duty:
                set_duty_cycle(duty, period)
                # Use _() and .format() for strings with variables
                logging.info(_("Updating duty cycle to {duty}%").format(duty=duty))
                last_duty = duty

        except Exception as e:
            # Use _() and .format() for strings with variables
            logging.error(_("Error in auto mode: {error}").format(error=e))

        time.sleep(interval)

def main():
    # Use _() for translatable strings in argparse descriptions and help text
    parser = argparse.ArgumentParser(description=_("PWM Fan Smart Controller (auto-loads config)"))
    parser.add_argument("--mode", choices=["auto", "manual"], default="auto", help=_("Select mode: auto or manual"))
    parser.add_argument("--interval", type=int, default=5, help=_("Temperature check interval in seconds (auto mode)"))
    parser.add_argument("--verbose", action="store_true", help=_("Enable verbose logging output"))
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if not os.path.exists(PWM_PATH):
        # Use _() for translatable strings
        logging.error(_("PWM device not found. Please ensure pwm0 is exported and enabled!"))
        exit(1)

    check_pwm_enabled()

    period = read_period()
    # Use _() and .format() for strings with variables
    logging.info(_("PWM period: {period} ns").format(period=period))

    def signal_handler(sig, frame):
        # Use _() for translatable strings
        logging.info(_("Received interrupt signal, terminating program."))
        exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    if args.mode == "auto":
        auto_mode(period, args.interval, args.verbose)
    else:
        # Use _() for translatable strings
        logging.info(_("Starting Manual Mode"))
        while True:
            try:
                # Use _() for translatable strings in input prompts
                user_input = input(_("Set duty cycle (%) > "))
                percent = float(user_input.strip())
                set_duty_cycle(percent, period)
                # Use _() and .format() for strings with variables
                logging.info(_("Manually setting duty cycle to {percent}%").format(percent=percent))
            except ValueError:
                # Use _() for translatable strings
                print(_("Please enter a valid number!"))
            except Exception as e:
                # Use _() and .format() for strings with variables
                logging.error(_("Error in manual mode: {error}").format(error=e))

if __name__ == "__main__":
    main()
