import asyncio
import logging
import threading
import sys
from control import ControlState
from normal_operation import normal_operation
from plug_functions import get_plug, get_battery_status
from config import DO_CALIBRATION_CYCLES, CALIBRATION_CYCLES
from calibration import calibration_already_done, run_calibration_cycles
from logger import setup_logging

logger = logging.getLogger(__name__)
control = ControlState()

async def async_main(shutdown_event: asyncio.Event):
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

    logger.info("Entering normal operation mode")

    await normal_operation(plug, shutdown_event, control)


def start_async_loop(shutdown_event: asyncio.Event):
    asyncio.run(async_main(shutdown_event))


if __name__ == "__main__":
    shutdown_event = asyncio.Event()

    # Start asyncio in background thread
    async_thread = threading.Thread(
        target=start_async_loop,
        args=(shutdown_event,),
        daemon=True,
    )
    async_thread.start()

    # Run tray in main thread (Windows safe)
    if sys.platform.startswith("win"):
        from windows_tray import run_tray
        run_tray(shutdown_event, control)
    else:
        # Non-Windows fallback: just block forever
        async_thread.join()
