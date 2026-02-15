import os
import logging
from time import ctime
import asyncio

from kasa import SmartPlug
from config import CALIBRATION_HARD_FLOOR, CALIBRATION_HOLD_FOR, CALIBRATION_MAX_CHARGE_SECONDS, CALIBRATION_MAX_DISCHARGE_SECONDS, CALIBRATION_PUSH_ON_COMPLETE, CALIBRATION_STALL_WINDOW, CALIBRATION_STATE_FILE, CALIBRATION_CHARGE_TO, CALIBRATION_POLL_SECONDS, CALIBRATION_DISCHARGE_TO
from emergency import notify_emergency
from plug_functions import ensure_plug_off, ensure_plug_on, get_battery_status

logger = logging.getLogger(__name__)
def calibration_already_done() -> bool:
    return os.path.exists(CALIBRATION_STATE_FILE)
        
def mark_calibration_done() -> None:
    with open(CALIBRATION_STATE_FILE, "w") as f:
        f.write(ctime())

async def run_calibration_cycles(plug: SmartPlug, cycles: int) -> None:
    logger.warning("Starting battery calibration: %d cycle(s)", cycles)

    loop = asyncio.get_running_loop()

    async def charge_to_target():
        logger.warning(
            "Calibration charge phase — target %d%%",
            CALIBRATION_CHARGE_TO,
        )

        phase_start = loop.time()

        while True:
            percent, _ = get_battery_status()

            if percent is None:
                logger.error("Battery sensor unavailable during charge phase")
                await asyncio.sleep(CALIBRATION_POLL_SECONDS)
                continue

            if percent >= CALIBRATION_CHARGE_TO:
                await ensure_plug_off(plug)
                logger.info("Reached %d%% — stopping charge", percent)
                return

            # Phase timeout safeguard
            if loop.time() - phase_start > CALIBRATION_MAX_CHARGE_SECONDS:
                logger.critical("Charge phase exceeded maximum duration")
                return

            await ensure_plug_on(plug)

            await asyncio.sleep(CALIBRATION_POLL_SECONDS)

    async def discharge_to_target():
        logger.warning(
            "Calibration discharge phase — target %d%%",
            CALIBRATION_DISCHARGE_TO,
        )

        phase_start = loop.time()

        while True:
            percent, _ = get_battery_status()

            if percent is None:
                logger.error("Battery sensor unavailable during discharge phase")
                await asyncio.sleep(CALIBRATION_POLL_SECONDS)
                continue

            # Hard safety floor — force charging immediately
            if percent <= CALIBRATION_HARD_FLOOR:
                logger.critical(
                    "Hard floor reached at %d%% — forcing plug ON",
                    percent,
                )
                await ensure_plug_on(plug)
                return  # Let Windows hibernate if it chooses

            if percent <= CALIBRATION_DISCHARGE_TO:
                logger.info("Reached %d%% — discharge complete", percent)
                return

            # Timeout safeguard
            if loop.time() - phase_start > CALIBRATION_MAX_DISCHARGE_SECONDS:
                logger.critical("Discharge phase exceeded maximum duration")
                await ensure_plug_on(plug)
                return

            await ensure_plug_off(plug)
            await asyncio.sleep(CALIBRATION_POLL_SECONDS)

    for cycle in range(1, cycles + 1):
        logger.warning("Calibration cycle %d/%d", cycle, cycles)

        await charge_to_target()
        await asyncio.sleep(CALIBRATION_HOLD_FOR)
        await discharge_to_target()
        await asyncio.sleep(60)

    else:
        # Final cycle ends fully charged
        logger.warning("Calibration final cycle — ending at full charge")

        await charge_to_target()
        await asyncio.sleep(CALIBRATION_HOLD_FOR)

    if CALIBRATION_PUSH_ON_COMPLETE:
        notify_emergency(
            "Battery Calibration Completed",
            "Calibration finished successfully and ended at full charge.",
        )

    logger.warning("Battery calibration completed — resuming normal operation")
    mark_calibration_done()