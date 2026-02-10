import os
import logging
from time import ctime
import asyncio
from config import CALIBRATION_STATE_FILE, CALIBRATION_CHARGE_TO, CALIBRATION_POLL_SECONDS, CALIBRATION_DISCHARGE_TO
from plug_functions import get_battery_status, ensure_plug_off, ensure_plug_on

logger = logging.getLogger(__name__)
def calibration_already_done():
    return os.path.exists(CALIBRATION_STATE_FILE)
        
def mark_calibration_done():
    with open(CALIBRATION_STATE_FILE, "w") as f:
        f.write(ctime())

async def run_calibration_cycles(plug, cycles: int):
    logger.warning(
        "Starting battery calibration: %d cycle(s)",
        cycles,
    )
    for cycle in range(1, cycles + 1):
        logger.warning("Calibration cycle %d/%d — charging to %d%%",
                        cycle, cycles, CALIBRATION_CHARGE_TO)
        # -------- CHARGE PHASE --------
        while True:
            percent, power_plugged = get_battery_status()
            if percent is None:
                await asyncio.sleep(CALIBRATION_POLL_SECONDS)
                continue
            if percent >= CALIBRATION_CHARGE_TO:
                await ensure_plug_off(plug)
                logger.info("Reached %d%% — stopping charge", percent)
                break
            await ensure_plug_on(plug)
            await asyncio.sleep(CALIBRATION_POLL_SECONDS)
        # rest at full
        await asyncio.sleep(60 * 60)
        logger.warning("Calibration cycle %d/%d — discharging to %d%%",
                        cycle, cycles, CALIBRATION_DISCHARGE_TO)
        # -------- DISCHARGE PHASE --------
        while True:
            percent, power_plugged = get_battery_status()
            if percent is None:
                await asyncio.sleep(CALIBRATION_POLL_SECONDS)
                continue
            await ensure_plug_off(plug)
            if percent <= CALIBRATION_DISCHARGE_TO:
                logger.info("Reached %d%% — discharge complete", percent)
                break
            await asyncio.sleep(CALIBRATION_POLL_SECONDS)
        # pause before next cycle
        await asyncio.sleep(60)
    logger.warning("Battery calibration completed — resuming normal operation")
