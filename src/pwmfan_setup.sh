#!/bin/bash
set -e

# Default configuration file path
CONFIG_FILE="/etc/pwmfan_setup.ini"

# Default values
PWMCHIP_PATH_DEFAULT="/sys/class/pwm/pwmchip0"
PWM_NUMBER_DEFAULT=0
DEFAULT_PERIOD_DEFAULT=50000
DEFAULT_DUTY_CYCLE_DEFAULT=25000

# Load configuration from file if it exists
if [ -f "$CONFIG_FILE" ]; then
  echo "Loading configuration from $CONFIG_FILE"
  # Source the config file securely
  set -a # Automatically export all variables subsequently defined or modified
  . "$CONFIG_FILE"
  set +a # Stop automatically exporting variables
else
  echo "Warning: Configuration file $CONFIG_FILE not found. Using default values."
fi

# Use loaded values or defaults
PWMCHIP=${PWMCHIP_PATH:-$PWMCHIP_PATH_DEFAULT}
PWM_NUM=${PWM_NUMBER:-$PWM_NUMBER_DEFAULT}
PERIOD=${DEFAULT_PERIOD:-$DEFAULT_PERIOD_DEFAULT}
DUTY_CYCLE=${DEFAULT_DUTY_CYCLE:-$DEFAULT_DUTY_CYCLE_DEFAULT}

PWM_DIR="$PWMCHIP/pwm$PWM_NUM"

# Check if PWMCHIP path exists
if [ ! -d "$PWMCHIP" ]; then
  echo "Error: PWM chip path $PWMCHIP does not exist."
  exit 1
fi

# Export pwmX if not already exported
if [ ! -d "$PWM_DIR" ]; then
  echo "Exporting pwm$PWM_NUM on $PWMCHIP..."
  echo $PWM_NUM > "$PWMCHIP/export"
  # Wait a bit for the directory to appear
  sleep 0.2
  if [ ! -d "$PWM_DIR" ]; then
    echo "Error: Failed to export pwm$PWM_NUM. Directory $PWM_DIR not found after export."
    exit 1
  fi
  echo "Successfully exported pwm$PWM_NUM."
else
    echo "pwm$PWM_NUM already exported."
fi

# Set period and duty_cycle
echo "Setting period to $PERIOD for $PWM_DIR..."
echo $PERIOD > "$PWM_DIR/period"
echo "Setting duty cycle to $DUTY_CYCLE for $PWM_DIR..."
echo $DUTY_CYCLE > "$PWM_DIR/duty_cycle"

# Enable PWM
echo "Enabling $PWM_DIR..."
echo 1 > "$PWM_DIR/enable"

echo "PWM setup complete for $PWM_DIR."

exit 0
