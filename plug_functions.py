import asyncio
import logging
import subprocess
import sys
from time import time
from typing import Optional, cast

import psutil

from emergency import notify_emergency
from kasa import Credentials, Discover, SmartPlug
from config import KASA_PASSWORD, KASA_USERNAME, PLUG_IP, PLUG_MAC

logger = logging.getLogger(__name__)

_CHARGE_VERIFY_TIMEOUT = 15


def _normalize_mac(mac: str) -> str:
    return mac.lower().replace("-", ":")


def _find_ip_by_mac_arp(mac: str) -> Optional[str]:
    """Look up the current IP for a MAC address from the OS ARP table.

    The ARP cache is maintained by the OS as a side-effect of normal local
    network traffic, so it often has the current IP even when UDP discovery
    is unreliable after a firmware update.
    """
    target = _normalize_mac(mac)
    try:
        if sys.platform.startswith("win"):
            result = subprocess.run(
                ["arp", "-a"], capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in result.stdout.splitlines():
                parts = line.split()
                # Windows format: "  <ip>  <mac>  dynamic"
                if len(parts) >= 2 and _normalize_mac(parts[1]) == target:
                    return parts[0]
        else:
            try:
                # /proc/net/arp: "<ip>  0x1  0x2  <mac>  *  <iface>"
                with open("/proc/net/arp") as f:
                    for line in f.readlines()[1:]:
                        parts = line.split()
                        if len(parts) >= 4 and _normalize_mac(parts[3]) == target:
                            return parts[0]
            except FileNotFoundError:
                result = subprocess.run(
                    ["arp", "-n"], capture_output=True, text=True, timeout=5
                )
                # arp -n format: "<ip>  ether  <mac>  C  <iface>"
                for line in result.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 3 and _normalize_mac(parts[2]) == target:
                        return parts[0]
    except Exception as e:
        logger.debug("ARP table lookup failed: %s", e)
    return None


async def get_plug() -> SmartPlug:
    credentials = Credentials(KASA_USERNAME, KASA_PASSWORD)

    # 1. UDP broadcast discovery by MAC — resolves current IP even after DHCP change
    plug = await find_plug_by_mac(PLUG_MAC)
    if plug:
        return plug
    logger.warning("MAC-based UDP discovery failed — trying ARP table")

    # 2. ARP table lookup — OS caches IP→MAC from background network traffic,
    #    giving us the current IP without needing UDP to reach the plug directly
    arp_ip = _find_ip_by_mac_arp(PLUG_MAC)
    if arp_ip:
        try:
            device = await Discover.discover_single(arp_ip, credentials=credentials)
            if device:
                plug = cast(SmartPlug, device)
                await plug.update()
                logger.info("Found plug via ARP table at %s", arp_ip)
                return plug
        except Exception as e:
            logger.warning("ARP-found IP %s unreachable: %s — trying config IP", arp_ip, e)
    else:
        logger.warning("MAC not in ARP table — trying config IP")

    # 3. Cached config IP — last resort; may be stale if DHCP assigned a new address
    try:
        device = await Discover.discover_single(PLUG_IP, credentials=credentials)
        if device:
            plug = cast(SmartPlug, device)
            await plug.update()
            logger.info("Found plug via cached config IP %s", PLUG_IP)
            return plug
    except Exception as e:
        logger.warning("Config IP %s failed: %s", PLUG_IP, e)

    raise RuntimeError("Smart plug not found")


async def find_plug_by_mac(mac: str, timeout: int = 5) -> Optional[SmartPlug]:
    credentials = Credentials(KASA_USERNAME, KASA_PASSWORD)
    target = _normalize_mac(mac)
    logger.info("Discovering smart plug by MAC: %s", target)
    devices = await Discover.discover(timeout=timeout, credentials=credentials)
    for dev in devices.values():
        if dev.mac and _normalize_mac(dev.mac) == target:
            logger.info("Found plug '%s' at %s (MAC %s)", dev.alias, dev.host, dev.mac)
            plug = cast(SmartPlug, dev)
            await plug.update()
            logger.info("Using plug via MAC discovery (%s)", plug.host)
            return plug
    return None


async def ensure_plug_on(plug: SmartPlug) -> None:
    for attempt in range(3):
        await plug.update()
        if not plug.is_on:
            logger.info("Turning smart plug ON (attempt %d)", attempt + 1)
            await plug.turn_on()
        charging_ok = await verify_charging_after_plug_on(timeout=_CHARGE_VERIFY_TIMEOUT)
        await plug.update()
        if charging_ok and plug.is_on:
            logger.info("Plug is ON and laptop is charging")
            return
        if attempt < 2:
            logger.warning(
                "Plug ON but laptop did NOT start charging within %ds (attempt %d), power-cycling",
                _CHARGE_VERIFY_TIMEOUT, attempt + 1,
            )
            await plug.turn_off()
            await asyncio.sleep(2)
        else:
            logger.critical(
                "Plug ON but laptop did NOT start charging within %ds (attempt 3)",
                _CHARGE_VERIFY_TIMEOUT,
            )
            notify_emergency(
                "Charging Failure",
                f"Smart plug turned ON but laptop did not start charging within {_CHARGE_VERIFY_TIMEOUT} seconds. "
                "Check cable, adapter, or outlet immediately.",
            )


async def verify_charging_after_plug_on(timeout: int = _CHARGE_VERIFY_TIMEOUT) -> bool:
    start = time()
    while time() - start < timeout:
        _, power_plugged = get_battery_status()
        if power_plugged:
            logger.info("Charging confirmed after plug ON")
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
        await asyncio.sleep(0.5)


def get_battery_status() -> tuple[Optional[float], Optional[bool]]:
    battery = psutil.sensors_battery()
    if battery is None:
        return None, None
    return battery.percent, battery.power_plugged
