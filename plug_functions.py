import asyncio
import ipaddress
import logging
import re
import socket
import subprocess
import sys
from time import time
from typing import Optional, cast

import psutil

from emergency import notify_emergency
from kasa import Credentials, Discover, SmartPlug
from config import (
    KASA_PASSWORD,
    KASA_USERNAME,
    PLUG_IP,
    PLUG_MAC,
    PLUG_IP_SECONDARY,
    PLUG_MAC_SECONDARY,
)

logger = logging.getLogger(__name__)

_CHARGE_VERIFY_TIMEOUT = 15


def _normalize_mac(mac: str) -> str:
    return mac.lower().replace("-", ":")


async def _test_plug_connection(plug: SmartPlug, expected_mac: str) -> bool:
    """Toggles the plug state to verify it's the expected plug."""
    logger.info("Verifying plug connection by toggling state...")
    original_state = plug.is_on
    await plug.turn_off()
    await asyncio.sleep(15)  # Wait for state change
    await plug.update()
    if plug.is_on:
        logger.warning("Plug did not turn off. Not the correct plug or issue.")
        return False

    await plug.turn_on()
    await asyncio.sleep(15)  # Wait for state change
    await plug.update()

    if not plug.is_on:
        logger.warning("Plug did not turn on. Not the correct plug or issue.")
        return False

    # Restore original state
    if not original_state:
        await plug.turn_off()

    logger.info("Plug verification successful.")
    return True

import re

def _find_ip_by_mac_arp(mac: str) -> Optional[str]:
    target = _normalize_mac(mac)
    # Safely matches any IPv4 address in a string
    ip_pattern = re.compile(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b')
    
    try:
        if sys.platform.startswith("win"):
            result = subprocess.run(
                ["arp", "-a"], capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            try:
                # Fast native read for Linux
                with open("/proc/net/arp") as f:
                    for line in f.readlines()[1:]:
                        parts = line.split()
                        if len(parts) >= 4 and _normalize_mac(parts[3]) == target:
                            return parts[0]
                return None # If we successfully read the file but found no match
            except FileNotFoundError:
                # macOS / BSD fallback
                result = subprocess.run(
                    ["arp", "-an"], capture_output=True, text=True, timeout=5
                )
                
        # Common parser for both Windows and macOS subprocess output
        for line in result.stdout.splitlines():
            if target in line.lower():
                match = ip_pattern.search(line)
                if match:
                    return match.group(0)
                    
    except Exception as e:
        logger.debug("ARP table lookup failed: %s", e)
    return None

def _get_local_subnets() -> list[tuple[str, str]]:
    """Return (address, netmask) pairs, filtering out known virtual adapters."""
    subnets = []
    CGNAT = ipaddress.ip_network("100.64.0.0/10")
    
    # Explicitly ignore virtual interfaces created by Docker, WSL, VMs, and VPNs
    ignore_terms = ["wsl", "docker", "hyper-v", "vmware", "virtualbox", "tailscale", "loopback", "pseudo", "veth"]
    
    for iface_name, addrs in psutil.net_if_addrs().items():
        # Check if the interface name matches any of our ignore terms
        if any(term in iface_name.lower() for term in ignore_terms):
            logger.debug("Skipping virtual interface: %s", iface_name)
            continue
            
        for addr in addrs:
            # Ignore IPv6, loopback, and Windows APIPA (169.254.x.x) self-assigned IPs
            if addr.family == socket.AF_INET and not addr.address.startswith("127.") and not addr.address.startswith("169.254."):
                try:
                    ip_addr_obj = ipaddress.ip_address(addr.address)
                    if ip_addr_obj in CGNAT:
                        continue 
                    subnets.append((addr.address, addr.netmask))
                except ValueError:
                    pass
                    
    return subnets


async def _ping_sweep_subnets() -> None:
    """Fast UDP sweep across subnets to warm the OS ARP cache."""
    subnets = _get_local_subnets()
    if not subnets:
        logger.warning("No local subnets found for network sweep")
        return
        
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)

    # Tells macOS/Linux kernels this socket is allowed to hit broadcast IPs
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    payload = b"{}" 
    
    sweep_count = 0
    logger.info("Starting UDP subnet sweep to warm ARP cache...")
    
    for address, netmask in subnets:
        try:
            network = ipaddress.IPv4Network(f"{address}/{netmask}", strict=False)
            
            # PREVENT ARP OVERFLOW: If the network is massive (like your /17), sweeping
            # 32,000+ IPs will instantly flush the Windows ARP cache, evicting the plug.
            # We restrict the fallback ARP sweep to the local /24 block (254 IPs).
            if network.num_addresses > 1024:
                logger.info("Subnet %s is too large for Windows ARP cache. Restricting sweep to local /24 block.", network)
                network = ipaddress.IPv4Network(f"{address}/24", strict=False)
                
            for ip in network.hosts():
                try:
                    sock.sendto(payload, (str(ip), 9999))
                    sweep_count += 1
                    if sweep_count % 1000 == 0:
                        await asyncio.sleep(0.01)
                except Exception:
                    pass
        except Exception as e:
            logger.warning("Failed to process subnet %s/%s: %s", address, netmask, e)
            
    sock.close()
    logger.info("UDP sweep complete: fired packets at %d IPs", sweep_count)
    await asyncio.sleep(0.5)


async def get_plug() -> SmartPlug:
    credentials = Credentials(KASA_USERNAME, KASA_PASSWORD)

    async def _try_connect_and_verify(
        ip: Optional[str], mac: str, is_primary: bool
    ) -> Optional[SmartPlug]:
        plug_type = "primary" if is_primary else "secondary"
        logger.info("Attempting to connect to %s plug (MAC: %s, IP: %s)", plug_type, mac, ip or "unknown")

        # 1. UDP broadcast discovery by MAC (Global + Directed)
        plug = await find_plug_by_mac(mac)
        if plug and await _test_plug_connection(plug, mac):
            logger.info("Found %s plug via MAC discovery at %s", plug_type, plug.host)
            return plug
        logger.warning("MAC-based UDP discovery failed for %s plug — trying ARP table", plug_type)

        # 2. ARP table lookup (cold cache)
        arp_ip = _find_ip_by_mac_arp(mac)
        if arp_ip:
            try:
                device = await Discover.discover_single(arp_ip, credentials=credentials)
                if device and device.mac and _normalize_mac(device.mac) == _normalize_mac(mac):
                    plug = cast(SmartPlug, device)
                    await plug.update()
                    if await _test_plug_connection(plug, mac):
                        logger.info("Found %s plug via ARP table at %s", plug_type, arp_ip)
                        return plug
            except Exception as e:
                logger.warning("ARP-found IP %s unreachable for %s plug: %s — sweeping subnet", arp_ip, plug_type, e)
        else:
            logger.warning("MAC not in ARP table for %s plug — sweeping subnet", plug_type)

        # 3. UDP sweep to warm the ARP cache, then try ARP lookup again
        await _ping_sweep_subnets()
        arp_ip = _find_ip_by_mac_arp(mac)
        if arp_ip:
            try:
                device = await Discover.discover_single(arp_ip, credentials=credentials)
                if device and device.mac and _normalize_mac(device.mac) == _normalize_mac(mac):
                    plug = cast(SmartPlug, device)
                    await plug.update()
                    if await _test_plug_connection(plug, mac):
                        logger.info("Found %s plug via UDP sweep + ARP at %s", plug_type, arp_ip)
                        return plug
            except Exception as e:
                logger.warning("Sweep ARP IP %s unreachable for %s plug: %s — trying config IP", arp_ip, plug_type, e)
        else:
            logger.warning("MAC not in ARP table for %s plug after sweep — trying config IP", plug_type)

        # 4. Cached config IP — last resort
        if ip:
            try:
                device = await Discover.discover_single(ip, credentials=credentials)
                if device and device.mac and _normalize_mac(device.mac) == _normalize_mac(mac):
                    plug = cast(SmartPlug, device)
                    await plug.update()
                    if await _test_plug_connection(plug, mac):
                        logger.info("Found %s plug via cached config IP %s", plug_type, ip)
                        return plug
            except Exception as e:
                logger.warning("Config IP %s failed for %s plug: %s", ip, plug_type, e)

        logger.warning("Failed to find and verify %s plug.", plug_type)
        return None

    primary_plug = await _try_connect_and_verify(PLUG_IP, PLUG_MAC, True)
    if primary_plug:
        return primary_plug

    secondary_plug = await _try_connect_and_verify(PLUG_IP_SECONDARY, PLUG_MAC_SECONDARY, False)
    if secondary_plug:
        return secondary_plug

    raise RuntimeError("Smart plug not found")


async def find_plug_by_mac(mac: str, timeout: int = 15) -> Optional[SmartPlug]:
    credentials = Credentials(KASA_USERNAME, KASA_PASSWORD)
    target_mac = _normalize_mac(mac)
    
    logger.info("Discovering smart plug by MAC: %s (Global Broadcast)", target_mac)
    devices = await Discover.discover(timeout=timeout, credentials=credentials)
    for dev in devices.values():
        if dev.mac and _normalize_mac(dev.mac) == target_mac:
            logger.info("Found plug '%s' at %s (MAC %s)", dev.alias, dev.host, dev.mac)
            plug = cast(SmartPlug, dev)
            await plug.update()
            return plug

    # If Global Broadcast gets swallowed by WSL/Docker, we explicitly target 
    # the directed broadcast address of the actual physical network adapters.
    logger.info("Global broadcast failed. Attempting Directed Broadcast on local subnets...")
    subnets = _get_local_subnets()
    for address, netmask in subnets:
        network = ipaddress.IPv4Network(f"{address}/{netmask}", strict=False)
        directed_bcast = str(network.broadcast_address)
        
        logger.info("Sending discovery broadcast specifically to %s", directed_bcast)
        try:
            devices = await Discover.discover(target=directed_bcast, timeout=timeout, credentials=credentials)
            for dev in devices.values():
                if dev.mac and _normalize_mac(dev.mac) == target_mac:
                    logger.info("Found plug via directed broadcast at %s", dev.host)
                    plug = cast(SmartPlug, dev)
                    await plug.update()
                    return plug
        except Exception as e:
            logger.debug("Directed broadcast failed on %s: %s", directed_bcast, e)
            
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