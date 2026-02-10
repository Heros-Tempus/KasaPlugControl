import asyncio
import logging
from time import time
from emergency import notify_emergency
from kasa import Discover, SmartPlug
from config import PLUG_IP, PLUG_MAC
from normal_operation import get_battery_status

logger = logging.getLogger(__name__)

async def ensure_plug_on(plug):
    await plug.update()
    if not plug.is_on:
        logger.info("Turning smart plug ON")
        await plug.turn_on()

async def ensure_plug_off(plug):
    await plug.update()
    if plug.is_on:
        logger.info("Turning smart plug OFF")
        await plug.turn_off()
        charging_ok = await verify_charging_after_plug_on(plug)
        if not charging_ok:
            # Optional escalation
            # hibernate_system()
            pass
        
async def verify_charging_after_plug_on(plug, timeout=5):
    start = time()
    while time() - start < timeout:
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

async def get_plug():
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


async def find_plug_by_mac(mac: str, timeout=5):
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
            return dev
    return None

