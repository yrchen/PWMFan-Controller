#!/usr/bin/env python3
import argparse
import gettext
import json
import locale
import logging
import os
import signal
import time

# Version Information
__version__ = "1.0.1"

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

# Configuration file path
CONFIG_FILE = "/etc/pwmfan_config.json"

# Default configuration values
DEFAULT_CONFIG = {
    "pwm_chip_path": "/sys/class/pwm/pwmchip0",
    "pwm_path": "/sys/class/pwm/pwmchip0/pwm0",
    "temp_sensor_path": "/sys/class/thermal/thermal_zone0/temp",
    "interval": 10,
    "temperature_to_duty": [
        {"temp": 45, "duty": 0},
        {"temp": 50, "duty": 10},
        {"temp": 55, "duty": 30},
        {"temp": 60, "duty": 80},
        {"temp": 65, "duty": 100}
    ]
}

# Read PWM period
def read_period(pwm_path):
    try:
        with open(os.path.join(pwm_path, "period"), "r") as f:
            return int(f.read().strip())
    except Exception as e:
        # Use _() and .format() for strings with variables
        logging.error(_("Failed to read PWM period from {path}: {error}").format(path=os.path.join(pwm_path, "period"), error=e))
        raise # Re-raise the exception after logging

# Set duty cycle (percentage)
def set_duty_cycle(percent, period, pwm_path):
    percent = max(0, min(100, percent))
    duty_ns = int(period * (percent / 100.0))
    try:
        with open(os.path.join(pwm_path, "duty_cycle"), "w") as f:
            f.write(str(duty_ns))
    except Exception as e:
        # Use _() and .format() for strings with variables
        logging.error(_("Failed to set duty cycle at {path}: {error}").format(path=os.path.join(pwm_path, "duty_cycle"), error=e))
        raise # Re-raise the exception after logging

# Read CPU temperature (°C)
def read_temperature(temp_sensor_path):
    try:
        with open(temp_sensor_path, "r") as f:
            temp_milli = int(f.read().strip())
            return temp_milli / 1000.0
    except Exception as e:
        # Use _() and .format() for strings with variables
        logging.error(_("Failed to read temperature from {path}: {error}").format(path=temp_sensor_path, error=e))
        raise # Re-raise the exception after logging

# Load configuration file
def load_config():
    config = DEFAULT_CONFIG.copy() # Start with defaults
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            # Update config with values from file, keeping defaults if keys are missing
            config.update(data)
            # Ensure curve is sorted
            if "temperature_to_duty" in data:
                config["temperature_to_duty"].sort(key=lambda x: x["temp"])
            # Use _() and .format() for strings with variables
            logging.info(_("Successfully loaded configuration file: {config_file}").format(config_file=CONFIG_FILE))
    except FileNotFoundError:
        logging.warning(_("Configuration file {config_file} not found, using default configuration.").format(config_file=CONFIG_FILE))
    except json.JSONDecodeError as e:
        logging.warning(_("Error decoding configuration file {config_file}: {error}, using default configuration.").format(config_file=CONFIG_FILE, error=e))
    except Exception as e:
        logging.warning(_("Failed to load configuration file {config_file}: {error}, using default configuration.").format(config_file=CONFIG_FILE, error=e))

    # Validate essential paths from the final config
    if not os.path.exists(config["pwm_path"]):
        logging.warning(_("Configured PWM path does not exist: {path}").format(path=config["pwm_path"]))
    if not os.path.exists(config["temp_sensor_path"]):
        logging.warning(_("Configured temperature sensor path does not exist: {path}").format(path=config["temp_sensor_path"]))

    return config

# Return duty cycle based on temperature
def temp_to_duty(temp_celsius, curve):
    for rule in curve:
        if temp_celsius < rule["temp"]:
            return rule["duty"]
    return curve[-1]["duty"]

def check_pwm_enabled(pwm_path):
    try:
        with open(os.path.join(pwm_path, "enable"), "r") as f:
            enabled = int(f.read().strip())
            if enabled != 1:
                # Use _() for translatable strings
                raise RuntimeError(_("PWM is not enabled (enable file is not 1 at {path})").format(path=os.path.join(pwm_path, "enable")))
    except FileNotFoundError:
         # Use _() for translatable strings
        logging.error(_("PWM enable file not found at {path}. Ensure PWM is exported.").format(path=os.path.join(pwm_path, "enable")))
        exit(1)
    except Exception as e:
        # Use _() and .format() for strings with variables
        logging.error(_("Failed to check PWM status at {path}: {error}").format(path=os.path.join(pwm_path, "enable"), error=e))
        exit(1)

def auto_mode(initial_config):
    config = initial_config
    last_config_mtime = 0
    last_duty = -1
    period = -1 # Initialize period

    # Use _() for translatable strings
    logging.info(_("Starting Auto Mode"))

    while True:
        try:
            # Check for configuration file updates
            current_mtime = 0
            if os.path.exists(CONFIG_FILE):
                try:
                    current_mtime = os.path.getmtime(CONFIG_FILE)
                except OSError as e:
                     logging.warning(_("Could not get mtime for config file {config_file}: {error}").format(config_file=CONFIG_FILE, error=e))

            if current_mtime != last_config_mtime:
                logging.info(_("Configuration file change detected, reloading configuration."))
                config = load_config() # Reload entire config
                last_config_mtime = current_mtime
                # Re-read period if config changed, in case pwm_path changed
                try:
                    check_pwm_enabled(config["pwm_path"]) # Check enablement with potentially new path
                    period = read_period(config["pwm_path"])
                    logging.info(_("PWM period: {period} ns").format(period=period))
                except Exception as e:
                    logging.error(_("Failed to re-initialize PWM after config reload: {error}").format(error=e))
                    # Decide if we should exit or try again later
                    time.sleep(config.get("interval", 10)) # Use interval from potentially new config, default 5
                    continue # Skip this cycle

            # Ensure period is valid before proceeding
            if period <= 0:
                 logging.warning(_("PWM period not valid ({period}), skipping cycle.").format(period=period))
                 time.sleep(config.get("interval", 10))
                 continue

            temp = read_temperature(config["temp_sensor_path"])
            duty = temp_to_duty(temp, config["temperature_to_duty"])

            if config.get("verbose"): # Check verbosity from config
                # Use _() and .format() for strings with variables
                logging.info(_("Temperature: {temp:.1f}°C => Calculated duty cycle: {duty}%").format(temp=temp, duty=duty))

            if duty != last_duty:
                set_duty_cycle(duty, period, config["pwm_path"])
                # Use _() and .format() for strings with variables
                logging.info(_("Updating duty cycle to {duty}%").format(duty=duty))
                last_duty = duty

        except Exception as e:
            # Use _() and .format() for strings with variables
            logging.error(_("Error in auto mode: {error}").format(error=e))
            # Avoid busy-looping on continuous errors
            time.sleep(config.get("interval", 10))

        time.sleep(config.get("interval", 10)) # Use interval from config

def main():
    # Use _() for translatable strings in argparse descriptions and help text
    parser = argparse.ArgumentParser(
        description=_("PWM Fan Smart Controller (loads config from {config_file})").format(config_file=CONFIG_FILE),
        prog=APP_NAME # Use APP_NAME for program name in help/version
    )
    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}', # Display program name and version
        help=_("Show program's version number and exit")
    )
    parser.add_argument("--mode", choices=["auto", "manual"], default="auto", help=_("Select mode: auto or manual"))
    # Removed --interval argument
    parser.add_argument("--verbose", action="store_true", help=_("Enable verbose logging output (overrides config setting)"))
    args = parser.parse_args()

    # Load configuration first
    config = load_config()

    # Setup logging - allow command line verbose to override config
    log_level = logging.INFO if args.verbose or config.get("verbose", False) else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    # Log the effective config being used (optional, consider redacting sensitive info if any)
    # logging.info(f"Effective configuration: {config}") # Be careful logging full config

    pwm_path = config["pwm_path"] # Get path from loaded config

    if not os.path.exists(pwm_path):
        # Use _() for translatable strings
        logging.error(_("PWM device path configured in {config_file} not found: {path}. Please ensure the path is correct and pwm0 is exported!").format(config_file=CONFIG_FILE, path=pwm_path))
        exit(1)

    try:
        check_pwm_enabled(pwm_path)
        period = read_period(pwm_path)
        # Use _() and .format() for strings with variables
        logging.info(_("PWM period: {period} ns").format(period=period))
    except Exception:
         # Error already logged in helper functions
         logging.error(_("Failed to initialize PWM device at {path}. Exiting.").format(path=pwm_path))
         exit(1)

    def signal_handler(sig, frame):
        # Use _() for translatable strings
        logging.info(_("Received interrupt signal, terminating program."))
        exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    if args.mode == "auto":
        # Pass the initial config dictionary
        auto_mode(config)
    else: # Manual Mode
        # Use _() for translatable strings
        logging.info(_("Starting Manual Mode"))
        while True:
            try:
                # Use _() for translatable strings in input prompts
                user_input = input(_("Set duty cycle (%) > "))
                percent = float(user_input.strip())
                set_duty_cycle(percent, period, pwm_path) # Pass pwm_path
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
