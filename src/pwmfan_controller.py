#!/usr/bin/env python3
import argparse
import gettext
import json
import locale
import logging
import os
import signal
import sys  # Import sys for exit
import time

# Version Information
__version__ = "1.0.7"

# Setup localization
APP_NAME = "pwmfan_controller"
# Assume locales dir is one level up from src/, adjust if needed for installation
# LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'locales') # Remove hardcoded path

try:
    # Try to set locale from environment
    locale.setlocale(locale.LC_ALL, "")
    lang_code, encoding = locale.getlocale()
    if lang_code:
        # Use detected language, let gettext find the standard locale dir
        lang = gettext.translation(APP_NAME, languages=[lang_code], fallback=True)
    else:
        # Fallback to English if no locale detected, let gettext find the standard locale dir
        lang = gettext.translation(APP_NAME, languages=["en"], fallback=True)
except (locale.Error, FileNotFoundError, TypeError):
    # Fallback to NullTranslations if locale setting fails, file not found, or lang_code is None
    lang = gettext.NullTranslations()

_ = lang.gettext  # Assign the translation function

# Configuration file path
CONFIG_FILE = "/etc/pwmfan_config.json"
RASPBERRY_PI_MODEL_PATH = "/sys/firmware/devicetree/base/model"

# Default configuration values
DEFAULT_CONFIG = {
    "pwm_chip_path": "/sys/class/pwm/pwmchip0",
    "pwm_path": "/sys/class/pwm/pwmchip0/pwm0",
    "temp_sensor_paths": ["/sys/class/thermal/thermal_zone0/temp"],
    "interval": 10,
    "verbose": True,
    "log_level": "WARNING",
    "temperature_to_duty": [
        {"temp": 45, "duty": 0},
        {"temp": 50, "duty": 10},
        {"temp": 55, "duty": 30},
        {"temp": 60, "duty": 80},
        {"temp": 65, "duty": 100},
    ],
}

# --- Enhanced Helper Functions with Detailed Error Handling ---


def read_sysfs_value(path):
    """Reads a value from a sysfs path with detailed error handling."""
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        logging.error(_("Sysfs path not found: {path}").format(path=path))
        raise
    except PermissionError:
        logging.error(_("Permission denied reading sysfs path: {path}").format(path=path))
        raise
    except OSError as e:
        logging.error(_("OS error reading sysfs path {path}: {error}").format(path=path, error=e))
        raise
    except Exception:
        logging.exception(
            _("Unexpected error reading sysfs path {path}").format(path=path)
        )  # Use logging.exception for traceback
        raise


def write_sysfs_value(path, value):
    """Writes a value to a sysfs path with detailed error handling."""
    try:
        with open(path, "w") as f:
            f.write(str(value))
            logging.debug(f"Successfully wrote '{value}' to {path}")
    except FileNotFoundError:
        logging.error(_("Sysfs path not found: {path}").format(path=path))
        raise
    except PermissionError:
        logging.error(_("Permission denied writing to sysfs path: {path}").format(path=path))
        raise
    except OSError as e:
        logging.error(_("OS error writing to sysfs path {path}: {error}").format(path=path, error=e))
        raise
    except Exception:
        logging.exception(
            _("Unexpected error writing to sysfs path {path}").format(path=path)
        )  # Use logging.exception for traceback
        raise


# Read PWM period
def read_period(pwm_path):
    period_path = os.path.join(pwm_path, "period")
    try:
        value = read_sysfs_value(period_path)
        period = int(value)
        if period <= 0:
            logging.error(_("Invalid PWM period value read from {path}: {value}").format(path=period_path, value=value))
            raise ValueError(_("PWM period must be positive"))
        logging.debug(f"Read PWM period: {period} from {period_path}")
        return period
    except ValueError as e:
        logging.error(
            _("Non-integer value read for PWM period from {path}. Value: '{value}'. Error: {error}").format(
                path=period_path, value=value, error=e
            )
        )
        raise
    except Exception:  # Catch exceptions from read_sysfs_value or int()
        # Error already logged by read_sysfs_value or above
        raise  # Re-raise to indicate failure


# Set duty cycle (percentage)
def set_duty_cycle(percent, period, pwm_path):
    duty_cycle_path = os.path.join(pwm_path, "duty_cycle")
    if not (0 <= percent <= 100):
        logging.warning(_("Duty cycle percent {percent}% out of range (0-100), clamping.").format(percent=percent))
        percent = max(0, min(100, percent))
    if period <= 0:
        logging.error(_("Cannot set duty cycle with invalid period: {period}").format(period=period))
        return  # Or raise an error, depending on desired behavior

    # --- Check if PWM is enabled before writing ---
    if not check_pwm_enabled(pwm_path):
        logging.warning(
            _("Attempted to set duty cycle while PWM is not enabled for {path}. Skipping write.").format(path=pwm_path)
        )
        return
    # --- End check ---

    duty_ns = int(period * (percent / 100.0))
    try:
        write_sysfs_value(duty_cycle_path, duty_ns)
    except Exception:
        # Error already logged by write_sysfs_value
        # Decide if we need to re-raise or just log
        logging.error(_("Failed to set duty cycle on {path}").format(path=duty_cycle_path))
        # Not re-raising here to potentially allow the loop to continue


# Read CPU temperature (°C) - Now handles multiple paths and returns max temp
def read_temperature(temp_sensor_paths):
    """Reads temperatures from a list of sysfs paths and returns the maximum valid temperature."""
    max_temp = -float("inf")  # Initialize with negative infinity
    valid_temp_found = False
    read_errors = 0

    for temp_sensor_path in temp_sensor_paths:
        try:
            value = read_sysfs_value(temp_sensor_path)  # Handles FileNotFoundError, PermissionError etc.
            temp_milli = int(value)
            temperature = temp_milli / 1000.0
            logging.debug(f"Read temperature: {temperature}°C from {temp_sensor_path}")
            max_temp = max(max_temp, temperature)
            valid_temp_found = True
        except ValueError as e:
            logging.error(
                _("Non-integer value read for temperature from {path}: {value}. Error: {error}").format(
                    path=temp_sensor_path, value=value, error=e
                )
            )
            read_errors += 1
        except (FileNotFoundError, PermissionError, OSError):
            # Error already logged by read_sysfs_value
            logging.warning(
                _("Failed to read temperature from {path}, skipping this sensor.").format(path=temp_sensor_path)
            )
            read_errors += 1
        except Exception:
            # Error already logged by read_sysfs_value
            logging.error(
                _("Unexpected error reading temperature from {path}, skipping.").format(path=temp_sensor_path)
            )
            read_errors += 1

    if not valid_temp_found:
        logging.error(
            _("Failed to read any valid temperature from configured paths: {paths}").format(paths=temp_sensor_paths)
        )
        return None  # Return None if no paths were readable

    logging.debug(f"Maximum temperature from {temp_sensor_paths}: {max_temp}°C")
    return max_temp


# Load configuration file
def load_config():
    """Loads configuration, applying hardware detection defaults first."""
    # --- Hardware Detection ---
    detected_model = detect_raspberry_pi_model()
    adjusted_default_config = DEFAULT_CONFIG.copy()  # Start with base defaults

    if detected_model and "Raspberry Pi 5" in detected_model:
        logging.info(_("Detected Raspberry Pi 5. Adjusting default temperature sensors."))
        rpi5_potential_zones = [
            "/sys/class/thermal/thermal_zone0/temp",  # CPU
            "/sys/class/thermal/thermal_zone1/temp",  # GPU? PMIC? (Depends on kernel/dt)
            "/sys/class/thermal/thermal_zone2/temp",  # PMIC? GPU? (Depends on kernel/dt)
            # Add more zones if necessary for RPi 5 variants
        ]
        rpi5_existing_zones = [p for p in rpi5_potential_zones if os.path.exists(p)]
        if rpi5_existing_zones:
            adjusted_default_config["temp_sensor_paths"] = rpi5_existing_zones
            logging.info(_("Using RPi 5 default temp sensors: {paths}").format(paths=rpi5_existing_zones))
        else:
            logging.warning(
                _("Detected RPi 5, but could not find expected additional thermal zones. Using base default.")
            )
    # Add logic here for other Pi models if needed (e.g., RPi 4 specific defaults)
    elif detected_model:
        logging.info(_("Detected {model}. Using standard default temperature sensor.").format(model=detected_model))
    else:
        logging.info(_("Could not detect specific Raspberry Pi model. Using standard default settings."))

    # --- Load User Configuration File ---
    # Start config with the (potentially hardware-adjusted) defaults
    config = adjusted_default_config
    config_loaded_successfully = False
    user_config_data = {}

    try:
        logging.debug(f"Attempting to load user configuration from: {CONFIG_FILE}")
        with open(CONFIG_FILE, "r") as f:
            user_config_data = json.load(f)
            logging.debug(f"Raw data loaded from config file: {user_config_data}")
            config_loaded_successfully = True
            logging.info(
                _("Successfully loaded user configuration file: {config_file}").format(config_file=CONFIG_FILE)
            )
            # Update the adjusted defaults with user settings (user settings take priority)
            config.update(user_config_data)
            logging.debug("Merged user config with defaults.")

    except FileNotFoundError:
        logging.warning(
            _(
                "User configuration file {config_file} not found. Using default configuration (potentially adjusted for hardware)."
            ).format(config_file=CONFIG_FILE)
        )
    except PermissionError:
        logging.error(
            _("Permission denied reading user configuration file: {config_file}. Using defaults.").format(
                config_file=CONFIG_FILE
            )
        )
    except json.JSONDecodeError as e:
        logging.error(
            _("Error decoding JSON user configuration file {config_file}: {error}. Using defaults.").format(
                config_file=CONFIG_FILE, error=e
            )
        )
    except Exception:
        logging.exception(
            _("Unexpected error loading user configuration file {config_file}. Using defaults.").format(
                config_file=CONFIG_FILE
            )
        )

    # --- Configuration Validation ---
    logging.debug(f"Validating final configuration: {config}")
    is_config_valid = True
    # Base default to compare against if user config had issues
    fallback_config = adjusted_default_config

    # Validate pwm_path
    pwm_key = "pwm_path"
    path_val = config.get(pwm_key)
    if not isinstance(path_val, str):
        logging.error(
            _("Config Error: '{key}' must be a string, but got {type}. Falling back to default: {fallback}").format(
                key=pwm_key, type=type(path_val).__name__, fallback=fallback_config[pwm_key]
            )
        )
        config[pwm_key] = fallback_config[pwm_key]
        is_config_valid = False
    else:
        pwm_dir = os.path.dirname(path_val)
        pwm_chip_dir = os.path.dirname(pwm_dir)  # Go one level higher for pwmchip path
        if not os.path.isdir(pwm_chip_dir):
            logging.warning(
                _("Parent PWM chip directory for '{key}' does not exist: {path}. PWM might not be available.").format(
                    key=pwm_key, path=pwm_chip_dir
                )
            )
        elif not os.path.exists(path_val):
            logging.warning(
                _("Configured path for '{key}' does not exist: {path}. It might need to be exported.").format(
                    key=pwm_key, path=path_val
                )
            )

    # Validate temp_sensor_paths
    temp_key = "temp_sensor_paths"
    paths_val = config.get(temp_key)
    if not isinstance(paths_val, list) or not paths_val:
        logging.error(
            _("Config Error: '{key}' must be a non-empty list of strings. Falling back to default: {fallback}").format(
                key=temp_key, fallback=fallback_config[temp_key]
            )
        )
        config[temp_key] = fallback_config[temp_key]
        is_config_valid = False
    else:
        valid_paths = []
        for i, path in enumerate(paths_val):
            if not isinstance(path, str):
                logging.error(
                    _(
                        "Config Error: Item at index {index} in '{key}' is not a string: {value}. Skipping this path."
                    ).format(index=i, key=temp_key, value=path)
                )
                # Don't mark config as invalid here, just skip the entry if others exist
                continue  # Skip this invalid path entry
            elif not os.path.exists(path):
                logging.warning(_("Configured path in '{key}' does not exist: {path}").format(key=temp_key, path=path))
            valid_paths.append(path)  # Add even non-existent paths, read_temperature will handle errors

        if not valid_paths:
            logging.error(
                _(
                    "Config Error: '{key}' contains no valid or existing paths after filtering. Falling back to default: {fallback}"
                ).format(key=temp_key, fallback=fallback_config[temp_key])
            )
            config[temp_key] = fallback_config[temp_key]
            is_config_valid = False
        elif len(valid_paths) < len(paths_val):
            # If some user-provided paths were skipped due to type error
            if config_loaded_successfully and temp_key in user_config_data:
                logging.warning(
                    _("Some paths provided by user in '{key}' were invalid and skipped.").format(key=temp_key)
                )
            config[temp_key] = valid_paths  # Update config with only the valid string paths

    # Validate interval
    interval_key = "interval"
    interval_val = config.get(interval_key)
    if not isinstance(interval_val, int) or interval_val <= 0:
        logging.error(
            _(
                "Config Error: '{key}' must be a positive integer, but got {value}. Falling back to default: {fallback}"
            ).format(key=interval_key, value=interval_val, fallback=fallback_config[interval_key])
        )
        config[interval_key] = fallback_config[interval_key]
        is_config_valid = False

    # Validate temperature curve
    curve_key = "temperature_to_duty"
    curve = config.get(curve_key)
    if not isinstance(curve, list) or not curve:
        logging.error(
            _("Config Error: '{key}' must be a non-empty list. Falling back to default curve.").format(key=curve_key)
        )
        config[curve_key] = fallback_config[curve_key]
        is_config_valid = False
    else:
        for i, rule in enumerate(curve):
            if (
                not isinstance(rule, dict)
                or "temp" not in rule
                or "duty" not in rule
                or not isinstance(rule["temp"], (int, float))
                or not isinstance(rule["duty"], (int, float))
                or not (0 <= rule["duty"] <= 100)
            ):
                logging.error(
                    _(
                        "Config Error: Invalid rule at index {index} in '{key}': {rule}. Falling back to default curve."
                    ).format(index=i, key=curve_key, rule=rule)
                )
                config[curve_key] = fallback_config[curve_key]
                is_config_valid = False
                break  # Stop checking curve rules
        else:  # If loop completed without break
            try:
                config[curve_key].sort(key=lambda x: x["temp"])
                logging.debug("Temperature curve sorted.")
            except Exception as e:
                logging.error(
                    _("Error sorting temperature curve: {error}. Falling back to default curve.").format(error=e)
                )
                config[curve_key] = fallback_config[curve_key]
                is_config_valid = False

    # --- Final Logging ---
    if config_loaded_successfully and not is_config_valid:
        logging.warning(
            _("User configuration from {config_file} contained errors. Used defaults for invalid entries.").format(
                config_file=CONFIG_FILE
            )
        )
    elif not config_loaded_successfully:
        # Already logged warning about missing file, maybe just info here
        logging.info(_("Using default configuration (potentially adjusted for hardware)."))
    else:  # Loaded successfully and validated (or user settings were valid)
        logging.info(_("Configuration loaded and validated successfully."))

    return config


# Return duty cycle based on temperature
def temp_to_duty(temp_celsius, curve):
    if temp_celsius is None:  # Handle case where temperature reading failed
        logging.warning(_("Cannot determine duty cycle because temperature reading failed."))
        return None  # Indicate failure

    if not curve:  # Should have been caught by validation, but double-check
        logging.error(_("Attempted to use empty temperature curve!"))
        return None

    # Ensure curve is sorted (validation should handle sorting, but defensive check)
    # curve.sort(key=lambda x: x["temp"]) # Already sorted in load_config

    selected_duty = curve[-1]["duty"]  # Default to highest duty if temp > all thresholds
    for rule in curve:
        try:
            if temp_celsius < rule["temp"]:
                selected_duty = rule["duty"]
                break
        except KeyError:
            logging.error(_("Malformed rule in curve (missing 'temp' or 'duty'): {rule}").format(rule=rule))
            # Potentially return None or fallback, here we continue loop hoping for a valid rule
        except TypeError:
            logging.error(_("Non-numeric 'temp' or 'duty' in curve rule: {rule}").format(rule=rule))

    # Clamp duty cycle just in case validation missed something
    selected_duty = max(0, min(100, selected_duty))
    logging.debug(f"Temp {temp_celsius}°C -> Duty {selected_duty}%")
    return selected_duty


def check_pwm_enabled(pwm_path):
    enable_path = os.path.join(pwm_path, "enable")
    try:
        value = read_sysfs_value(enable_path)
        enabled = int(value)
        if enabled != 1:
            logging.error(
                _("PWM is not enabled (read {value} from {path}). Please ensure PWM is exported and enabled.").format(
                    value=value, path=enable_path
                )
            )
            return False
        logging.debug(f"PWM confirmed enabled via {enable_path}")
        return True
    except ValueError as e:
        logging.error(
            _("Non-integer value read for PWM enable status from {path}: {value}. Error: {error}").format(
                path=enable_path, value=value, error=e
            )
        )
        return False
    except FileNotFoundError:
        # Already logged by read_sysfs_value
        logging.error(_("PWM enable file not found at {path}. Cannot check PWM status.").format(path=enable_path))
        return False
    except Exception:
        # Error logged by read_sysfs_value or above
        logging.error(_("Failed to check PWM status at {path}").format(path=enable_path))
        return False


def auto_mode(initial_config):
    """Runs the fan controller in automatic mode based on temperature."""
    config = initial_config
    last_config_mtime = 0
    last_duty = -1
    period = -1  # Initialize period
    consecutive_read_errors = 0
    max_consecutive_read_errors = 5  # Exit if too many errors occur

    logging.info(_("Starting Auto Mode with configuration:"))
    # Log key config values safely
    for key in ["pwm_path", "temp_sensor_paths", "interval", "log_level"]:  # Updated keys
        logging.info(f"  {key}: {config.get(key)}")
    logging.info(f"  temperature_to_duty: {config.get('temperature_to_duty')}")

    # --- Get initial config file modification time ---
    try:
        if os.path.exists(CONFIG_FILE):
            last_config_mtime = os.path.getmtime(CONFIG_FILE)
            logging.debug(f"Initial config file mtime: {last_config_mtime}")
        else:
            logging.debug("Config file does not exist initially.")
    except OSError as e:
        logging.warning(
            _("Could not get initial mtime for config file {config_file}: {error}").format(
                config_file=CONFIG_FILE, error=e
            )
        )
        # last_config_mtime remains 0, will trigger reload if file appears later

    # --- Initial PWM Setup ---
    def initialize_pwm(current_config):
        nonlocal period
        pwm_path = current_config["pwm_path"]
        if not check_pwm_enabled(pwm_path):
            logging.error(_("Initial PWM check failed. Auto mode cannot run."))
            return False
        try:
            period = read_period(pwm_path)
            logging.info(_("PWM initialized. Period: {period} ns").format(period=period))
            return True
        except Exception:
            logging.error(
                _("Failed to read initial PWM period from {path}. Auto mode cannot run.").format(path=pwm_path)
            )
            return False

    if not initialize_pwm(config):
        # Consider exiting or entering a safe state if PWM fails initially
        logging.critical(_("PWM initialization failed. Exiting auto mode."))
        sys.exit(1)  # Exit if PWM cannot be set up
    # --- End Initial PWM Setup ---

    while True:
        logging.debug(_("Auto mode loop iteration started."))  # Changed level to DEBUG
        interval = config.get("interval", 10)  # Get interval for this iteration
        pwm_path = config["pwm_path"]
        temp_sensor_paths = config["temp_sensor_paths"]  # Use list of paths

        try:
            # Check for configuration file updates
            current_mtime = 0
            if os.path.exists(CONFIG_FILE):
                try:
                    current_mtime = os.path.getmtime(CONFIG_FILE)
                except OSError as e:
                    logging.warning(
                        _("Could not get mtime for config file {config_file}: {error}").format(
                            config_file=CONFIG_FILE, error=e
                        )
                    )

            if current_mtime != last_config_mtime:
                logging.info(_("Configuration file change detected, reloading configuration."))
                config = load_config()  # Reload and re-validate config
                last_config_mtime = current_mtime
                # Re-initialize PWM if config changed
                logging.info(_("Re-initializing PWM due to config change."))
                if not initialize_pwm(config):
                    logging.error(_("Failed to re-initialize PWM after config reload. Skipping cycle."))
                    time.sleep(interval)
                    continue
                else:
                    # Reset last_duty as the curve might have changed
                    last_duty = -1
                    logging.info(_("PWM re-initialized successfully."))

            # Ensure period is valid before proceeding (could be invalid after failed reload)
            if period <= 0:
                logging.warning(
                    _("PWM period not valid ({period}), attempting re-initialization.").format(period=period)
                )
                if not initialize_pwm(config):
                    logging.error(_("Failed to re-initialize PWM period. Skipping cycle."))
                    time.sleep(interval)
                    continue
                if period <= 0:  # Still invalid after re-init
                    logging.error(_("PWM period still invalid after re-initialization. Skipping cycle."))
                    time.sleep(interval)
                    continue

            # --- Read Temperature and Set Duty Cycle ---
            temp = read_temperature(temp_sensor_paths)  # Pass the list of paths

            if temp is None:
                # Failed to read temperature (error logged in read_temperature)
                consecutive_read_errors += 1
                logging.warning(
                    _(
                        "Temperature read failed ({consecutive_read_errors}/{max_consecutive_read_errors} consecutive errors)."
                    ).format(
                        consecutive_read_errors=consecutive_read_errors,
                        max_consecutive_read_errors=max_consecutive_read_errors,
                    )
                )
                if consecutive_read_errors >= max_consecutive_read_errors:
                    logging.critical(_("Exceeded maximum consecutive temperature read errors. Exiting."))
                    sys.exit(1)
                # Optionally set a safe duty cycle here, e.g., 100%
                # set_duty_cycle(100, period, pwm_path)
                time.sleep(interval)
                continue  # Skip this iteration
            else:
                consecutive_read_errors = 0  # Reset error count on success

            duty = temp_to_duty(temp, config["temperature_to_duty"])

            if duty is None:
                logging.error(_("Failed to calculate duty cycle. Skipping update."))
                # Keep last duty cycle?
                time.sleep(interval)
                continue

            # Log temperature and calculated duty if verbose
            if config.get("verbose"):
                logging.info(
                    _("Temperature: {temp:.1f}°C => Calculated duty cycle: {duty}%").format(temp=temp, duty=duty)
                )

            if duty != last_duty:
                logging.info(
                    _(
                        "Temperature {temp:.1f}°C triggers change: Updating duty cycle from {old_duty}% to {new_duty}%."
                    ).format(temp=temp, old_duty=last_duty, new_duty=duty)
                )
                set_duty_cycle(duty, period, pwm_path)  # Error handling is inside set_duty_cycle
                # We might want to confirm the write was successful by reading back duty_cycle if critical
                last_duty = duty
            else:
                logging.debug(f"Temperature {temp:.1f}°C, duty cycle {duty}% unchanged.")

        except Exception as e:
            # Catch unexpected errors in the main loop
            logging.exception(_("Unexpected error in auto mode main loop: {error}").format(error=e))
            # Avoid busy-looping on continuous errors
            time.sleep(interval * 2)  # Sleep longer after unexpected error

        # --- Wait for next interval ---
        logging.debug(f"Sleeping for {interval} seconds.")
        time.sleep(interval)


def manual_mode(initial_config):
    """Runs the fan controller in manual mode, allowing user input."""
    logging.info(_("Starting Manual Mode"))
    # Use the validated config from main()
    config = initial_config
    pwm_path = config["pwm_path"]
    period = -1
    # Initialize PWM for manual mode
    try:
        if not check_pwm_enabled(pwm_path):
            logging.error(_("PWM check failed. Manual mode cannot run."))
            sys.exit(1)
        period = read_period(pwm_path)
        logging.info(_("PWM initialized for manual mode. Period: {period} ns").format(period=period))
    except Exception:
        # Error logged in called functions
        logging.critical(_("Failed to initialize PWM for manual mode. Exiting.").format(path=pwm_path))
        sys.exit(1)

    # Input loop
    while True:
        try:
            user_input = input(_("Set duty cycle (%) or 'quit' > "))
            cmd = user_input.strip().lower()
            if cmd == "quit":
                logging.info(_("Exiting manual mode."))
                break
            # Allow setting 0% duty cycle
            percent = float(cmd)
            # Validation happens inside set_duty_cycle (clamping)
            set_duty_cycle(percent, period, pwm_path)
            # Log the clamped value if possible, or just the requested value
            logging.info(_("Manually setting duty cycle towards {percent}%.").format(percent=percent))

        except ValueError:
            print(_("Invalid input. Please enter a number (0-100) or 'quit'."))
        except EOFError:  # Handle Ctrl+D
            logging.info(_("EOF received, exiting manual mode."))
            break
        except KeyboardInterrupt:  # Handle Ctrl+C during input
            logging.info(_("Keyboard interrupt during input, exiting manual mode."))
            break
        except Exception as e:
            logging.exception(_("Error in manual mode input loop: {error}").format(error=e))


def detect_raspberry_pi_model():
    """Detects the Raspberry Pi model by reading the device tree."""
    try:
        model_str = read_sysfs_value(RASPBERRY_PI_MODEL_PATH)
        # The model string might contain null characters, strip them
        model_str_cleaned = model_str.replace("\x00", "").strip()
        logging.debug(f"Detected Raspberry Pi model: {model_str_cleaned}")
        return model_str_cleaned
    except (FileNotFoundError, PermissionError, OSError):
        logging.warning(
            _("Could not read Raspberry Pi model from {path}. Hardware detection unavailable.").format(
                path=RASPBERRY_PI_MODEL_PATH
            )
        )
        return None
    except Exception:
        logging.exception(
            _("Unexpected error detecting Raspberry Pi model from {path}.").format(path=RASPBERRY_PI_MODEL_PATH)
        )
        return None


def main():
    # Use _() for translatable strings in argparse descriptions and help text
    parser = argparse.ArgumentParser(
        description=_("PWM Fan Smart Controller (config: {config_file})").format(config_file=CONFIG_FILE),
        prog=APP_NAME,  # Use APP_NAME for program name in help/version
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",  # Display program name and version
        help=_("Show program's version number and exit"),
    )
    parser.add_argument("--mode", choices=["auto", "manual"], default="auto", help=_("Select mode: auto or manual"))
    # Removed --interval argument
    parser.add_argument(
        "--verbose",
        action="store_true",
        help=_("Enable verbose logging output (overrides config log_level to INFO)"),  # Clarified help
    )
    args = parser.parse_args()

    # --- Initial Configuration Load & Validation ---
    # load_config() now incorporates hardware detection defaults
    config = load_config()

    # --- Logging Setup ---
    # Allow command line verbose to override config OR default
    log_level_name = config.get("log_level", "WARNING").upper()  # Allow setting log level in config
    try:
        # Map name to level
        level = logging.getLevelName(log_level_name)
    except ValueError:
        logging.warning(
            _("Invalid log_level '{log_level_name}' in config. Using WARNING.").format(log_level_name=log_level_name)
        )
        level = logging.WARNING

    # Command line --verbose overrides to INFO
    if args.verbose:
        level = logging.INFO
        log_format = "[%(levelname)s %(filename)s:%(lineno)d] %(message)s"  # More detail if verbose
    else:
        log_format = "[%(levelname)s] %(message)s"  # Simpler format for normal operation

    logging.basicConfig(
        level=level,
        format=log_format,  # Use selected format
        force=True,  # Force re-configuration if basicConfig was called implicitly before
    )
    logging.info(
        _("Logging initialized. Effective level: {level_name}").format(
            level_name=logging.getLevelName(logging.getLogger().getEffectiveLevel())
        )
    )

    # --- RPi Firmware Warning ---
    # Keep the existing warning based on thermal zones found in the *final* config
    try:
        # Check based on the final loaded config's temp paths
        final_temp_paths = config.get("temp_sensor_paths", [])
        has_multiple_zones = (
            len(final_temp_paths) > 1
            or any("thermal_zone1" in p for p in final_temp_paths)
            or os.path.exists("/sys/class/thermal/thermal_zone1")
        )

        if has_multiple_zones and "Raspberry Pi 5" in (detect_raspberry_pi_model() or ""):
            # Show warning only if multiple zones detected AND it looks like an RPi 5
            logging.warning("-----------------------------------------------------")
            logging.warning(_("Multiple thermal zones detected (potentially Raspberry Pi 5 or similar)."))
            logging.warning(
                _("If using the official Raspberry Pi Active Cooler, fan control might be handled by the firmware.")
            )
            logging.warning(_("This script might conflict or have no effect in that case."))
            logging.warning("-----------------------------------------------------")
    except Exception as e:
        logging.debug(f"Could not perform RPi 5 check: {e}")

    # --- Signal Handling ---
    def signal_handler(sig, frame):
        logging.info(
            _("Received signal {signal_name} ({signal_number}), terminating program.").format(
                signal_name=signal.Signals(sig).name, signal_number=sig
            )
        )
        # Optionally try to set a safe fan speed before exiting
        # try:
        #     period = read_period(config["pwm_path"])
        #     set_duty_cycle(100, period, config["pwm_path"])
        #     logging.info(_("Set fan to 100% before exiting."))
        # except Exception as e:
        #     logging.warning(_("Could not set fan speed on exit: {error}").format(error=e))
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    logging.debug("Signal handlers registered for SIGINT and SIGTERM.")

    # --- Mode Dispatch ---
    if args.mode == "auto":
        auto_mode(config)  # Pass the final validated config
    elif args.mode == "manual":
        manual_mode(config)  # Pass the final validated config
    else:
        logging.error(_("Invalid mode selected: {mode}").format(mode=args.mode))
        sys.exit(1)

    logging.info(_("Program finished."))


if __name__ == "__main__":
    # --- Global Exception Handling ---
    try:
        main()
    except SystemExit as e:
        # Catch sys.exit() to allow clean exit logging if needed
        logging.info(_("Exiting with code {code}").format(code=e.code))
        sys.exit(e.code)  # Re-exit with the original code
    except KeyboardInterrupt:
        logging.info(_("Keyboard interrupt detected during initialization/shutdown."))
        sys.exit(130)  # Standard exit code for Ctrl+C
    except Exception:
        # Catch-all for unexpected errors during startup/main execution
        logging.exception(_("Unhandled exception during program execution!"))
        sys.exit(1)  # General error exit code
