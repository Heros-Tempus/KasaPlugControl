import asyncio
import ipaddress
import logging
import socket
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


def _get_local_subnets() -> list[tuple[str, str]]:
    """Return (address, netmask) pairs for all active non-loopback IPv4 interfaces."""
    subnets = []
    CGNAT = ipaddress.ip_network("100.64.0.0/10")
    for addrs in psutil.net_if_addrs().values():
        for addr in addrs:
            if ipaddress.ip_address(addr.address) in CGNAT:
                continue  # skip Tailscale and any other CGNAT interface
            if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                subnets.append((addr.address, addr.netmask))
    return subnets


async def _ping_one(ip: str) -> None:
    if sys.platform.startswith("win"):
        proc = await asyncio.create_subprocess_exec(
            "ping", "-n", "1", "-w", "200", ip,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", "1", ip,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    await proc.wait()


async def _ping_sweep_subnets() -> None:
    """Ping every host on all local subnets to warm the OS ARP cache."""
    subnets = _get_local_subnets()
    if not subnets:
        logger.warning("No local subnets found for ping sweep")
        return
    tasks = []
    for address, netmask in subnets:
        network = ipaddress.IPv4Network(f"{address}/{netmask}", strict=False)
        tasks.extend(_ping_one(str(ip)) for ip in network.hosts())
    logger.info("Ping sweep: sending %d pings across %d subnet(s)", len(tasks), len(subnets))
    await asyncio.gather(*tasks)
    logger.info("Ping sweep complete")


async def get_plug() -> SmartPlug:
    credentials = Credentials(KASA_USERNAME, KASA_PASSWORD)

    # 1. UDP broadcast discovery by MAC — resolves current IP even after DHCP change
    plug = await find_plug_by_mac(PLUG_MAC)
    if plug:
        return plug
    logger.warning("MAC-based UDP discovery failed — trying ARP table")

    # 2. ARP table lookup (cold cache)
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
            logger.warning("ARP-found IP %s unreachable: %s — sweeping subnet", arp_ip, e)
    else:
        logger.warning("MAC not in ARP table — sweeping subnet")

    # 3. Ping sweep to warm the ARP cache, then try ARP lookup again
    await _ping_sweep_subnets()
    arp_ip = _find_ip_by_mac_arp(PLUG_MAC)
    if arp_ip:
        try:
            device = await Discover.discover_single(arp_ip, credentials=credentials)
            if device:
                plug = cast(SmartPlug, device)
                await plug.update()
                logger.info("Found plug via ping sweep + ARP at %s", arp_ip)
                return plug
        except Exception as e:
            logger.warning("Ping-sweep ARP IP %s unreachable: %s — trying config IP", arp_ip, e)
    else:
        logger.warning("MAC not in ARP table after ping sweep — trying config IP")

    # 4. Cached config IP — last resort; may be stale if DHCP assigned a new address
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
    """ Turns the plug on and confirms the laptop begins drawing power within the
    timeout. If charging is not detected, the plug is power-cycled (off then
    on again) - a stuck relay or momentary firmware glitch can leave the plug
    reporting ON while the outlet still delivers no power.
    """
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
