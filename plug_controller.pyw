import asyncio
import logging
from normal_operation import normal_operation
from plug_functions import get_plug, get_battery_status
from config import DO_CALIBRATION_CYCLES, CALIBRATION_CYCLES
from calibration import calibration_already_done, run_calibration_cycles, mark_calibration_done
from logger import setup_logging

logger = logging.getLogger(__name__)

async def main():
    setup_logging()
    logger.info("Battery charge controller starting (normal mode)")
    plug = await get_plug()        
    percent, power_plugged = get_battery_status()
    logger.info(
        "Startup state: %s%%, power_plugged=%s",
        percent,
        power_plugged,
    )
    if DO_CALIBRATION_CYCLES and not calibration_already_done():
        await run_calibration_cycles(plug, CALIBRATION_CYCLES)
        mark_calibration_done()
    logger.info("Entering normal operation mode")
    await normal_operation(plug)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        logging.exception("Fatal unhandled exception")
        raise
