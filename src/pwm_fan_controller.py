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
__version__ = "1.0.4"

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
    "verbose": True,
    "temperature_to_duty": [
        {"temp": 45, "duty": 0},
        {"temp": 50, "duty": 10},
        {"temp": 55, "duty": 30},
        {"temp": 60, "duty": 80},
        {"temp": 65, "duty": 100}
    ]
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
        logging.exception(_("Unexpected error reading sysfs path {path}").format(path=path)) # Use logging.exception for traceback
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
        logging.exception(_("Unexpected error writing to sysfs path {path}").format(path=path)) # Use logging.exception for traceback
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
        logging.error(_("Non-integer value read for PWM period from {path}. Value: '{value}'. Error: {error}").format(path=period_path, value=value, error=e))
        raise
    except Exception: # Catch exceptions from read_sysfs_value or int()
        # Error already logged by read_sysfs_value or above
        raise # Re-raise to indicate failure

# Set duty cycle (percentage)
def set_duty_cycle(percent, period, pwm_path):
    duty_cycle_path = os.path.join(pwm_path, "duty_cycle")
    if not (0 <= percent <= 100):
         logging.warning(_("Duty cycle percent {percent}% out of range (0-100), clamping.").format(percent=percent))
         percent = max(0, min(100, percent))
    if period <= 0:
        logging.error(_("Cannot set duty cycle with invalid period: {period}").format(period=period))
        return # Or raise an error, depending on desired behavior

    duty_ns = int(period * (percent / 100.0))
    try:
        write_sysfs_value(duty_cycle_path, duty_ns)
    except Exception:
        # Error already logged by write_sysfs_value
        # Decide if we need to re-raise or just log
        logging.error(_("Failed to set duty cycle on {path}").format(path=duty_cycle_path))
        # Not re-raising here to potentially allow the loop to continue

# Read CPU temperature (°C)
def read_temperature(temp_sensor_path):
    try:
        value = read_sysfs_value(temp_sensor_path)
        temp_milli = int(value)
        temperature = temp_milli / 1000.0
        logging.debug(f"Read temperature: {temperature}°C from {temp_sensor_path}")
        return temperature
    except ValueError as e:
        logging.error(_("Non-integer value read for temperature from {path}: {value}. Error: {error}").format(path=temp_sensor_path, value=value, error=e))
        return None # Return None to indicate failure but allow continuation
    except Exception:
        # Error already logged by read_sysfs_value
        logging.error(_("Failed to read temperature from {path}").format(path=temp_sensor_path))
        return None # Return None to indicate failure

# Load configuration file
def load_config():
    config = DEFAULT_CONFIG.copy() # Start with defaults
    config_loaded_successfully = False
    try:
        logging.debug(f"Attempting to load configuration from: {CONFIG_FILE}")
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            logging.debug(f"Raw data loaded from config file: {data}")
            # Update config with values from file, keeping defaults if keys are missing
            config.update(data)
            config_loaded_successfully = True
            logging.info(_("Successfully loaded and merged configuration file: {config_file}").format(config_file=CONFIG_FILE))

    except FileNotFoundError:
        logging.warning(_("Configuration file {config_file} not found, using default configuration.").format(config_file=CONFIG_FILE))
    except PermissionError:
        logging.error(_("Permission denied reading configuration file: {config_file}, using default configuration.").format(config_file=CONFIG_FILE))
    except json.JSONDecodeError as e:
        logging.error(_("Error decoding JSON configuration file {config_file}: {error}, using default configuration.").format(config_file=CONFIG_FILE, error=e))
    except Exception:
        logging.exception(_("Unexpected error loading configuration file {config_file}, using default configuration.").format(config_file=CONFIG_FILE))

    # --- Configuration Validation ---
    logging.debug(f"Validating configuration: {config}")
    is_config_valid = True

    # Validate paths (must be string and exist)
    for key in ["pwm_path", "temp_sensor_path"]:
        path_val = config.get(key)
        if not isinstance(path_val, str):
            logging.error(_("Configuration error: '{key}' must be a string, but got {type}. Using default.").format(key=key, type=type(path_val).__name__))
            config[key] = DEFAULT_CONFIG[key] # Fallback to default
            is_config_valid = False
        elif not os.path.exists(path_val):
            # This might be okay if the device appears later, so use warning
            logging.warning(_("Configured path for '{key}' does not exist: {path}").format(key=key, path=path_val))
            # No fallback here, let subsequent checks handle it

    # Validate interval (must be positive integer)
    interval_val = config.get("interval")
    if not isinstance(interval_val, int) or interval_val <= 0:
        logging.error(_("Configuration error: 'interval' must be a positive integer, but got {value}. Using default {default}.").format(value=interval_val, default=DEFAULT_CONFIG['interval']))
        config["interval"] = DEFAULT_CONFIG["interval"]
        is_config_valid = False

    # Validate temperature curve (must be list of dicts with temp/duty numbers)
    curve = config.get("temperature_to_duty")
    if not isinstance(curve, list) or not curve:
        logging.error(_("Configuration error: 'temperature_to_duty' must be a non-empty list. Using default curve."))
        config["temperature_to_duty"] = DEFAULT_CONFIG["temperature_to_duty"]
        is_config_valid = False
    else:
        for i, rule in enumerate(curve):
            if not isinstance(rule, dict) or 'temp' not in rule or 'duty' not in rule or \
               not isinstance(rule['temp'], (int, float)) or not isinstance(rule['duty'], (int, float)) or \
               not (0 <= rule['duty'] <= 100):
                logging.error(_("Configuration error: Invalid rule at index {index} in 'temperature_to_duty': {rule}. Rule must be a dict with numeric 'temp' and 'duty' (0-100). Using default curve.").format(index=i, rule=rule))
                config["temperature_to_duty"] = DEFAULT_CONFIG["temperature_to_duty"]
                is_config_valid = False
                break # Stop checking curve rules
        else: # If loop completed without break
            try:
                 config["temperature_to_duty"].sort(key=lambda x: x["temp"])
                 logging.debug("Temperature curve sorted.")
            except Exception as e:
                 logging.error(_("Error sorting temperature curve: {error}. Using default curve.").format(error=e))
                 config["temperature_to_duty"] = DEFAULT_CONFIG["temperature_to_duty"]
                 is_config_valid = False

    if config_loaded_successfully and not is_config_valid:
        logging.warning(_("Configuration loaded from {config_file} contained errors. Using defaults for invalid entries.").format(config_file=CONFIG_FILE))
    elif not config_loaded_successfully:
         logging.info(_("Using default configuration."))
    else:
        logging.info(_("Configuration validated successfully."))

    return config

# Return duty cycle based on temperature
def temp_to_duty(temp_celsius, curve):
    if temp_celsius is None: # Handle case where temperature reading failed
        logging.warning(_("Cannot determine duty cycle because temperature reading failed."))
        return None # Indicate failure

    if not curve: # Should have been caught by validation, but double-check
        logging.error(_("Attempted to use empty temperature curve!"))
        return None

    # Ensure curve is sorted (validation should handle sorting, but defensive check)
    # curve.sort(key=lambda x: x["temp"]) # Already sorted in load_config

    selected_duty = curve[-1]['duty'] # Default to highest duty if temp > all thresholds
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
            logging.error(_("PWM is not enabled (read {value} from {path}). Please ensure PWM is exported and enabled.").format(value=value, path=enable_path))
            return False
        logging.debug(f"PWM confirmed enabled via {enable_path}")
        return True
    except ValueError as e:
        logging.error(_("Non-integer value read for PWM enable status from {path}: {value}. Error: {error}").format(path=enable_path, value=value, error=e))
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
    config = initial_config
    last_config_mtime = 0
    last_duty = -1
    period = -1 # Initialize period
    consecutive_read_errors = 0
    max_consecutive_read_errors = 5 # Exit if too many errors occur

    logging.info(_("Starting Auto Mode with configuration:"))
    # Log key config values safely
    for key in ['pwm_path', 'temp_sensor_path', 'interval', 'verbose']:
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
        logging.warning(_("Could not get initial mtime for config file {config_file}: {error}").format(config_file=CONFIG_FILE, error=e))
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
            logging.error(_("Failed to read initial PWM period from {path}. Auto mode cannot run.").format(path=pwm_path))
            return False

    if not initialize_pwm(config):
        # Consider exiting or entering a safe state if PWM fails initially
        logging.critical(_("PWM initialization failed. Exiting auto mode."))
        sys.exit(1) # Exit if PWM cannot be set up
    # --- End Initial PWM Setup ---


    while True:
        logging.debug(_("Auto mode loop iteration started.")) # Changed level to DEBUG
        interval = config.get("interval", 10) # Get interval for this iteration
        pwm_path = config["pwm_path"]
        temp_sensor_path = config["temp_sensor_path"]

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
                config = load_config() # Reload and re-validate config
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
                 logging.warning(_("PWM period not valid ({period}), attempting re-initialization.").format(period=period))
                 if not initialize_pwm(config):
                     logging.error(_("Failed to re-initialize PWM period. Skipping cycle."))
                     time.sleep(interval)
                     continue
                 if period <= 0: # Still invalid after re-init
                     logging.error(_("PWM period still invalid after re-initialization. Skipping cycle."))
                     time.sleep(interval)
                     continue

            # --- Read Temperature and Set Duty Cycle --- 
            temp = read_temperature(temp_sensor_path)

            if temp is None:
                # Failed to read temperature (error logged in read_temperature)
                consecutive_read_errors += 1
                logging.warning(_("Temperature read failed ({consecutive_read_errors}/{max_consecutive_read_errors} consecutive errors).").format(consecutive_read_errors=consecutive_read_errors, max_consecutive_read_errors=max_consecutive_read_errors))
                if consecutive_read_errors >= max_consecutive_read_errors:
                    logging.critical(_("Exceeded maximum consecutive temperature read errors. Exiting."))
                    sys.exit(1)
                # Optionally set a safe duty cycle here, e.g., 100%
                # set_duty_cycle(100, period, pwm_path)
                time.sleep(interval)
                continue # Skip this iteration
            else:
                consecutive_read_errors = 0 # Reset error count on success

            duty = temp_to_duty(temp, config["temperature_to_duty"])

            if duty is None:
                 logging.error(_("Failed to calculate duty cycle. Skipping update."))
                 # Keep last duty cycle?
                 time.sleep(interval)
                 continue

            # Log temperature and calculated duty if verbose
            if config.get("verbose"):
                logging.info(_("Temperature: {temp:.1f}°C => Calculated duty cycle: {duty}%").format(temp=temp, duty=duty))

            if duty != last_duty:
                logging.info(_("Temperature {temp:.1f}°C triggers change: Updating duty cycle from {old_duty}% to {new_duty}%.").format(temp=temp, old_duty=last_duty, new_duty=duty))
                set_duty_cycle(duty, period, pwm_path) # Error handling is inside set_duty_cycle
                # We might want to confirm the write was successful by reading back duty_cycle if critical
                last_duty = duty
            else:
                 logging.debug(f"Temperature {temp:.1f}°C, duty cycle {duty}% unchanged.")

        except Exception as e:
            # Catch unexpected errors in the main loop
            logging.exception(_("Unexpected error in auto mode main loop: {error}").format(error=e))
            # Avoid busy-looping on continuous errors
            time.sleep(interval * 2) # Sleep longer after unexpected error

        # --- Wait for next interval --- 
        logging.debug(f"Sleeping for {interval} seconds.")
        time.sleep(interval)

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

    # --- Initial Configuration Load --- 
    # Load configuration first - errors handled and logged within load_config
    config = load_config()

    # --- Setup Logging --- 
    # Allow command line verbose to override config OR default
    log_level_name = config.get("log_level", "WARNING").upper() # Allow setting log level in config
    try:
        # Map name to level
        level = logging.getLevelName(log_level_name)
    except ValueError:
        logging.warning(_("Invalid log_level '{log_level_name}' in config. Using WARNING.").format(log_level_name=log_level_name))
        level = logging.WARNING

    # Command line --verbose overrides to INFO
    if args.verbose:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d] %(message)s", # Added filename/lineno
        force=True # Force re-configuration if basicConfig was called implicitly before
    )
    logging.info(_("Logging initialized. Effective level: {level_name}").format(level_name=logging.getLevelName(logging.getLogger().getEffectiveLevel())))

    # --- Signal Handling --- 
    def signal_handler(sig, frame):
        logging.info(_("Received signal {signal_name} ({signal_number}), terminating program.").format(signal_name=signal.Signals(sig).name, signal_number=sig))
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

    # --- Mode Selection --- 
    if args.mode == "auto":
        auto_mode(config)
    elif args.mode == "manual":
        logging.info(_("Starting Manual Mode"))
        # Manual mode needs initial PWM setup too
        pwm_path = config["pwm_path"]
        period = -1
        try:
            if not check_pwm_enabled(pwm_path):
                 logging.error(_("PWM check failed. Manual mode cannot run."))
                 sys.exit(1)
            period = read_period(pwm_path)
            logging.info(_("PWM initialized for manual mode. Period: {period} ns").format(period=period))
        except Exception:
            logging.error(_("Failed to initialize PWM for manual mode. Exiting.").format(path=pwm_path))
            sys.exit(1)

        while True:
            try:
                user_input = input(_("Set duty cycle (%) or 'quit' > "))
                if user_input.strip().lower() == 'quit':
                    logging.info(_("Exiting manual mode."))
                    break
                percent = float(user_input.strip())
                set_duty_cycle(percent, period, pwm_path) # Error handling inside
                logging.info(_("Manually setting duty cycle to {percent}%.").format(percent=percent))
            except ValueError:
                print(_("Invalid input. Please enter a number (0-100) or 'quit'."))
            except EOFError: # Handle Ctrl+D
                 logging.info(_("EOF received, exiting manual mode."))
                 break
            except KeyboardInterrupt: # Handle Ctrl+C during input
                logging.info(_("Keyboard interrupt during input, exiting manual mode."))
                break
            except Exception as e:
                logging.exception(_("Error in manual mode input loop: {error}").format(error=e))
    else:
         # Should not happen due to argparse choices
         logging.error(_("Invalid mode selected: {mode}").format(mode=args.mode))
         sys.exit(1)

    logging.info(_("Program finished."))

if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
         # Catch sys.exit() to allow clean exit logging if needed
         logging.info(_("Exiting with code {code}").format(code=e.code))
         sys.exit(e.code) # Re-exit with the original code
    except KeyboardInterrupt:
        logging.info(_("Keyboard interrupt detected during initialization/shutdown."))
        sys.exit(130) # Standard exit code for Ctrl+C
    except Exception:
        # Catch-all for unexpected errors during startup/main execution
        logging.exception(_("Unhandled exception during program execution!"))
        sys.exit(1) # General error exit code
