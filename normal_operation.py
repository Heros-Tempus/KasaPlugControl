import asyncio
from time import time
import logging
from typing import Optional
from kasa import SmartPlug
import wmi
from config import NORMAL_CHARGE_OFF_ABOVE, NORMAL_CHARGE_ON_BELOW, VIGILANCE_GRACE_SECONDS, VIGILANCE_MAX_PERCENT, VIGILANCE_MIN_PERCENT
from emergency import hibernate_system
from plug_functions import ensure_plug_off, ensure_plug_on, get_battery_status

logger = logging.getLogger(__name__)

async def enforce_normal_policy(plug: SmartPlug, percent: Optional[float]) -> None:
    if percent is None:
        return
    if percent <= NORMAL_CHARGE_ON_BELOW:
        logger.info(f"Percent is {percent}")
        await ensure_plug_on(plug)
    elif percent >= NORMAL_CHARGE_OFF_ABOVE:
        logger.info(f"Percent is {percent}")
        await ensure_plug_off(plug)

async def normal_operation(plug: SmartPlug) -> None:
    """
    Normal operation:
      - Event-driven (WMI) with periodic timeout fallback
      - Logs any change > 1%
      - If a drop > 10% is detected between checks, immediately turns plug ON
      - Respects manual overrides (user-forced charge or discharge)
    """
    logger.info("Starting normal operation")
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
        logger.info(
            "Initial state: %d%%, power_plugged=%s",
            last_percent,
            last_power_state,
        )
    while True:
        # Wait for battery change or timeout
        try:
            watcher(timeout_ms=4000)
        except Exception:
            await asyncio.sleep(1)
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
            logger.error("Plug update failed: %s", e)
            continue
        plug_is_on = plug.is_on
        # Enter vigilance
        if VIGILANCE_MIN_PERCENT < percent < VIGILANCE_MAX_PERCENT and not vigilant:
            vigilant = True
            vigilance_started_at = time()
            logger.warning(
                "Battery at %d%% — entering vigilance mode (5s grace)",
                percent,
            )
        # Exit vigilance if charging or recovered
        if vigilant and (plug_is_on or percent >= VIGILANCE_MAX_PERCENT):
            vigilant = False
            vigilance_started_at = None
            logger.info(
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
            elapsed = time() - (vigilance_started_at if vigilance_started_at else time())
            if elapsed >= VIGILANCE_GRACE_SECONDS:
                logger.critical(
                    "Battery dropped from %d%% to %d%% after %.1fs without charging — EMERGENCY",
                    last_percent,
                    percent,
                    elapsed,
                )
                hibernate_system()
                return
            else:
                logger.warning(
                    "Battery drop detected during vigilance (%.1fs into grace window)",
                    elapsed,
                )
        # Log significant changes
        if last_percent is not None and abs(percent - last_percent) > 1:
            logger.info(
                "Battery changed: %d%% → %d%%, power_plugged=%s, plug_is_on=%s",
                last_percent,
                percent,
                power_plugged,
                plug_is_on,
            )
        # Safety: sudden drop >10%
        if last_percent is not None and (last_percent - percent) > 10:
            logger.error(
                "Refund the Purchase: battery dropped from %d%% to %d%%",
                last_percent,
                percent,
            )
            await ensure_plug_on(plug)
        await enforce_normal_policy(plug, percent)
        last_percent = percent
        last_power_state = power_plugged
