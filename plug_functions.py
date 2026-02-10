import logging
from time import time
import psutil
import asyncio
from emergency import notify_emergency
from kasa import Discover, SmartPlug
from config import PLUG_IP, PLUG_MAC
from typing import Optional, cast

logger = logging.getLogger(__name__)

async def ensure_plug_on(plug: SmartPlug) -> None:
    for attempt in range(3):
        await plug.update()
        if not plug.is_on:
            logger.info("Turning smart plug ON (attempt %d)", attempt + 1)
            await plug.turn_on()
            charging_ok = await verify_charging_after_plug_on(timeout=5)
            await plug.update()
            if not charging_ok and plug.is_on:

                if attempt == 0:
                    logger.warning("Plug ON but laptop did NOT start charging within %ds", 5)
                if attempt == 1:
                    logger.warning("Plug ON but laptop did NOT start charging within %ds (attempt 2)", 5)
                if attempt == 2:
                    logger.critical("Plug ON but laptop did NOT start charging within %ds (attempt 3)", 5)
                    notify_emergency(
                        "Charging Failure",
                        "Smart plug turned ON but laptop did not start charging within 5 seconds. "
                        "Check cable, adapter, or outlet immediately.",
                    )
            elif charging_ok and plug.is_on:
                logger.info("Plug is ON and laptop is charging")
                break

async def verify_charging_after_plug_on(timeout=5) -> bool:
    start = time()
    while time() - start < timeout:
        _, power_plugged = get_battery_status()
        if power_plugged:
            logging.info("Charging confirmed after plug ON")
            return True
        await asyncio.sleep(0.5)
    return False

async def ensure_plug_off(plug: SmartPlug) -> None:
    for attempt in range(3):
        await plug.update()
        if not plug.is_on:
            logger.info("Plug is already OFF")
            return
        logger.info("Turning smart plug OFF (attempt %d)", attempt + 1)
        await plug.turn_off()
        await asyncio.sleep(0.5)  # Brief pause before checking status

async def get_plug() -> SmartPlug:
    plug = await find_plug_by_mac(PLUG_MAC)
    if not plug:
        logger.warning("Failed to find smart plug by MAC address %s", PLUG_MAC)
        try:
            plug = SmartPlug(PLUG_IP)
            await plug.update()
            logger.info("Using plug via cached IP %s", PLUG_IP)
            return plug
        except Exception:
            logger.warning("Failed to initialize plug via cached IP %s", PLUG_IP)
            raise RuntimeError("Smart plug not found")
    await plug.update()
    logger.info("Using plug via MAC discovery (%s)", plug.host)
    return plug


async def find_plug_by_mac(mac: str, timeout=5) -> Optional[SmartPlug]:
    mac = mac.lower()
    logger.info("Discovering smart plug by MAC: %s", mac)
    devices = await Discover.discover(timeout=timeout)
    for dev in devices.values():
        if dev.mac and dev.mac.lower() == mac:
            logger.info(
                "Found plug '%s' at %s (MAC %s)",
                dev.alias,
                dev.host,
                dev.mac,
            )
            return cast(SmartPlug, dev)
    return None


def get_battery_status() -> tuple[Optional[float], Optional[bool]]:
    battery = psutil.sensors_battery()
    if battery is None:
        return None, None
    return battery.percent, battery.power_plugged