import os
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import wmi
import psutil
import requests
import subprocess
import time
from kasa import Discover
from kasa import SmartPlug

from config import *

def calibration_already_done():
    return os.path.exists(CALIBRATION_STATE_FILE)

def mark_calibration_done():
    with open(CALIBRATION_STATE_FILE, "w") as f:
        f.write(time.ctime())

def notify_emergency(title: str, message: str):
    try:
        requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": PUSHOVER_APP_TOKEN,
                "user": PUSHOVER_USER_KEY,
                "title": title,
                "message": message,
                "priority": 1,  # high priority
            },
            timeout=5,
        )
    except Exception as e:
        logging.error("Failed to send Pushover alert: %s", e)

async def verify_charging_after_plug_on(plug, timeout=5):
    start = time.time()
    while time.time() - start < timeout:
        percent, power_plugged = get_battery_status()
        if power_plugged:
            logging.info("Charging confirmed after plug ON")
            return True
        await asyncio.sleep(0.5)
    logging.critical("Plug ON but laptop did NOT start charging within %ds", timeout)
    notify_emergency(
        "Charging Failure",
        "Smart plug turned ON but laptop did not start charging within 5 seconds. "
        "Check cable, adapter, or outlet immediately.",
    )
    return False

async def find_plug_by_mac(mac: str, timeout=5):
    mac = mac.lower()
    logging.info("Discovering smart plug by MAC: %s", mac)
    devices = await Discover.discover(timeout=timeout)
    for dev in devices.values():
        if dev.mac and dev.mac.lower() == mac:
            logging.info(
                "Found plug '%s' at %s (MAC %s)",
                dev.alias,
                dev.host,
                dev.mac,
            )
            return dev
    return None


def hibernate_system():
    logging.critical("Battery emergency detected — hibernating system immediately")
    subprocess.run(
        ["shutdown", "/h", "/f"],
        check=False
    )

def setup_logging():
    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=25 * 1024,   # 25 KB
        backupCount=1
    )
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    )
    handler.setFormatter(formatter)
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler],
    )

def get_battery_status():
    battery = psutil.sensors_battery()
    if battery is None:
        return None, None
    return battery.percent, battery.power_plugged

async def ensure_plug_on(plug):
    await plug.update()
    if not plug.is_on:
        logging.info("Turning smart plug ON")
        await plug.turn_on()

async def ensure_plug_off(plug):
    await plug.update()
    if plug.is_on:
        logging.info("Turning smart plug OFF")
        await plug.turn_off()
        charging_ok = await verify_charging_after_plug_on(plug)
        if not charging_ok:
            # Optional escalation
            # hibernate_system()
            pass

async def enforce_normal_policy(plug, percent):
    if percent is None:
        return
    if percent <= NORMAL_CHARGE_ON_BELOW:
        logging.info(f"Percent is {percent}")
        await ensure_plug_on(plug)
    elif percent >= NORMAL_CHARGE_OFF_ABOVE:
        logging.info(f"Percent is {percent}")
        await ensure_plug_off(plug)

async def get_plug():
    plug = await find_plug_by_mac(PLUG_MAC)
    if not plug:
        logging.warning("Failed to find smart plug by MAC address %s", PLUG_MAC)
        try:
            plug = SmartPlug(PLUG_IP)
            await plug.update()
            logging.info("Using plug via cached IP %s", PLUG_IP)
            return plug
        except Exception:
            logging.warning("Failed to initialize plug via cached IP %s", PLUG_IP)
            raise RuntimeError("Smart plug not found")
    await plug.update()
    logging.info("Using plug via MAC discovery (%s)", plug.host)
    return plug

async def run_calibration_cycles(plug, cycles: int):
    logging.warning(
        "Starting battery calibration: %d cycle(s)",
        cycles,
    )
    for cycle in range(1, cycles + 1):
        logging.warning("Calibration cycle %d/%d — charging to %d%%",
                        cycle, cycles, CALIBRATION_CHARGE_TO)
        # -------- CHARGE PHASE --------
        while True:
            percent, power_plugged = get_battery_status()
            if percent is None:
                await asyncio.sleep(CALIBRATION_POLL_SECONDS)
                continue
            if percent >= CALIBRATION_CHARGE_TO:
                await ensure_plug_off(plug)
                logging.info("Reached %d%% — stopping charge", percent)
                break
            await ensure_plug_on(plug)
            await asyncio.sleep(CALIBRATION_POLL_SECONDS)
        # rest at full
        await asyncio.sleep(60 * 60)
        logging.warning("Calibration cycle %d/%d — discharging to %d%%",
                        cycle, cycles, CALIBRATION_DISCHARGE_TO)
        # -------- DISCHARGE PHASE --------
        while True:
            percent, power_plugged = get_battery_status()
            if percent is None:
                await asyncio.sleep(CALIBRATION_POLL_SECONDS)
                continue
            await ensure_plug_off(plug)
            if percent <= CALIBRATION_DISCHARGE_TO:
                logging.info("Reached %d%% — discharge complete", percent)
                break
            await asyncio.sleep(CALIBRATION_POLL_SECONDS)
        # pause before next cycle
        await asyncio.sleep(60)
    logging.warning("Battery calibration completed — resuming normal operation")

async def normal_operation(plug):
    """
    Normal operation:
      - Event-driven (WMI) with periodic timeout fallback
      - Logs any change > 1%
      - If a drop > 10% is detected between checks, immediately turns plug ON
      - Respects manual overrides (user-forced charge or discharge)
    """
    logging.info("Starting normal operation")
    c = wmi.WMI()
    watcher = c.watch_for(
        notification_type="Modification",
        wmi_class="Win32_Battery",
    )
    last_percent, last_power_state = get_battery_status()
    await enforce_normal_policy(plug, last_percent)
    vigilant = False
    vigilance_started_at = None
    if last_percent is not None:
        logging.info(
            "Initial state: %d%%, power_plugged=%s",
            last_percent,
            last_power_state,
        )
    while True:
        # Wait for battery change or timeout
        try:
            watcher(timeout_ms=5000)  # 5 seconds
        except Exception:
            c = wmi.WMI()
            watcher = c.watch_for(
                notification_type="Modification",
                wmi_class="Win32_Battery",
            )
        percent, power_plugged = get_battery_status()
        if percent is None:
            continue
        if percent == last_percent and power_plugged == last_power_state:
            continue
        try:
            await plug.update()
        except Exception as e:
            logging.error("Plug update failed: %s", e)
            continue
        plug_is_on = plug.is_on
        # Enter vigilance
        if VIGILANCE_MIN_PERCENT < percent < VIGILANCE_MAX_PERCENT and not vigilant:
            vigilant = True
            vigilance_started_at = time.time()
            logging.warning(
                "Battery at %d%% — entering vigilance mode (5s grace)",
                percent,
            )
        # Exit vigilance if charging or recovered
        if vigilant and (plug_is_on or percent >= VIGILANCE_MAX_PERCENT):
            vigilant = False
            vigilance_started_at = None
            logging.info(
                "Exiting vigilance mode (plug_is_on=%s, battery=%d%%)",
                plug_is_on,
                percent,
            )
        # Emergency: battery drops during vigilance AFTER grace window
        if (
            vigilant
            and last_percent is not None
            and percent < last_percent
            and not plug_is_on
        ):
            elapsed = time.time() - (vigilance_started_at if vigilance_started_at else 0)
            if elapsed >= VIGILANCE_GRACE_SECONDS:
                logging.critical(
                    "Battery dropped from %d%% to %d%% after %.1fs without charging — EMERGENCY",
                    last_percent,
                    percent,
                    elapsed,
                )
                hibernate_system()
                return
            else:
                logging.warning(
                    "Battery drop detected during vigilance (%.1fs into grace window)",
                    elapsed,
                )
        # Log significant changes
        if last_percent is not None and abs(percent - last_percent) > 1:
            logging.info(
                "Battery changed: %d%% → %d%%, power_plugged=%s, plug_is_on=%s",
                last_percent,
                percent,
                power_plugged,
                plug_is_on,
            )
        # Safety: sudden drop >10%
        if last_percent is not None and (last_percent - percent) > 10:
            logging.error(
                "Refund the Purchase: battery dropped from %d%% to %d%%",
                last_percent,
                percent,
            )
            await ensure_plug_on(plug)
            plug_is_on = True
        await enforce_normal_policy(plug, percent)
        last_percent = percent
        last_power_state = power_plugged

async def main():
    setup_logging()
    logging.info("Battery charge controller starting (normal mode)")
    plug = await get_plug()        
    percent, power_plugged = get_battery_status()
    logging.info(
        "Startup state: %s%%, power_plugged=%s",
        percent,
        power_plugged,
    )
    if DO_CALIBRATION_CYCLES and not calibration_already_done():
        await run_calibration_cycles(plug, CALIBRATION_CYCLES)
        mark_calibration_done()
    logging.info("Entering normal operation mode")
    await normal_operation(plug)

if __name__ == "__main__":
    asyncio.run(main())
