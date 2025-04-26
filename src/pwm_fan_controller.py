#!/usr/bin/env python3
import os
import time
import argparse
import signal
import json
import logging

# PWM sysfs 路徑
PWM_CHIP_PATH = "/sys/class/pwm/pwmchip0"
PWM_PATH = os.path.join(PWM_CHIP_PATH, "pwm0")

# CPU 溫度讀取路徑
TEMP_SENSOR_PATH = "/sys/class/thermal/thermal_zone0/temp"

# 設定檔路徑
CONFIG_FILE = "/etc/pwmfan_config.json"

# 內建預設曲線
DEFAULT_CURVE = [
    {"temp": 40, "duty": 20},
    {"temp": 50, "duty": 40},
    {"temp": 60, "duty": 70},
    {"temp": 70, "duty": 100},
]

# 讀取 period
def read_period():
    with open(os.path.join(PWM_PATH, "period"), "r") as f:
        return int(f.read().strip())

# 設定 duty cycle（百分比）
def set_duty_cycle(percent, period):
    percent = max(0, min(100, percent))
    duty_ns = int(period * (percent / 100.0))
    with open(os.path.join(PWM_PATH, "duty_cycle"), "w") as f:
        f.write(str(duty_ns))

# 讀取 CPU 溫度（°C）
def read_temperature():
    with open(TEMP_SENSOR_PATH, "r") as f:
        temp_milli = int(f.read().strip())
        return temp_milli / 1000.0

# 讀取設定檔
def load_curve_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            curve = data.get("temperature_to_duty", [])
            if not curve:
                logging.warning("設定檔缺少 'temperature_to_duty'，使用預設曲線")
                return DEFAULT_CURVE
            curve.sort(key=lambda x: x["temp"])
            logging.info(f"成功載入設定檔 {CONFIG_FILE}")
            return curve
    except Exception as e:
        logging.warning(f"讀取設定檔失敗: {e}，使用預設曲線")
        return DEFAULT_CURVE

# 根據溫度回傳 duty cycle
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
                raise RuntimeError("PWM 尚未啟用 (enable=1)")
    except Exception as e:
        logging.error(f"檢查 PWM 狀態失敗: {e}")
        exit(1)

def auto_mode(period, interval, verbose):
    last_config_mtime = 0
    curve = DEFAULT_CURVE
    last_duty = -1

    logging.info("啟動自動模式 (Auto Mode)")

    while True:
        try:
            # 檢查設定檔更新
            if os.path.exists(CONFIG_FILE):
                mtime = os.path.getmtime(CONFIG_FILE)
                if mtime != last_config_mtime:
                    curve = load_curve_config()
                    last_config_mtime = mtime

            temp = read_temperature()
            duty = temp_to_duty(temp, curve)

            if verbose:
                logging.info(f"溫度: {temp:.1f}°C => 應設定轉速 {duty}%")

            if duty != last_duty:
                set_duty_cycle(duty, period)
                logging.info(f"更新轉速到 {duty}% duty cycle")
                last_duty = duty

        except Exception as e:
            logging.error(f"自動模式執行錯誤: {e}")

        time.sleep(interval)

def main():
    parser = argparse.ArgumentParser(description="PWM 風扇智能控制器 (自動載入設定)")
    parser.add_argument("--mode", choices=["auto", "manual"], default="auto", help="選擇模式：auto 或 manual")
    parser.add_argument("--interval", type=int, default=5, help="自動模式溫度讀取間隔（秒）")
    parser.add_argument("--verbose", action="store_true", help="開啟詳細日誌輸出")
    args = parser.parse_args()

    # 設定 logging
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if not os.path.exists(PWM_PATH):
        logging.error("找不到 PWM 裝置，請確認 pwm0 已匯出(export)並啟用！")
        exit(1)

    check_pwm_enabled()

    period = read_period()
    logging.info(f"PWM period: {period} ns")

    def signal_handler(sig, frame):
        logging.info("收到中斷訊號，結束程式")
        exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    if args.mode == "auto":
        auto_mode(period, args.interval, args.verbose)
    else:
        logging.info("啟動手動模式 (Manual Mode)")
        while True:
            try:
                user_input = input("設定轉速 (%) > ")
                percent = float(user_input.strip())
                set_duty_cycle(percent, period)
                logging.info(f"手動設定轉速 {percent}%")
            except ValueError:
                print("請輸入有效的數字！")
            except Exception as e:
                logging.error(f"手動模式錯誤: {e}")

if __name__ == "__main__":
    main()
