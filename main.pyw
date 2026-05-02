import asyncio
import logging
import threading
from time import sleep

from control import ControlState
from normal_operation import normal_operation
from plug_functions import get_plug, get_battery_status
from config import DO_CALIBRATION_CYCLES, CALIBRATION_CYCLES
from calibration import calibration_already_done, run_calibration_cycles
from logger import setup_logging

logger = logging.getLogger(__name__)
control = ControlState()

async def async_main(shutdown_event: threading.Event):
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


def start_async_loop(shutdown_event: threading.Event, loop_holder: dict):
    # create and set event loop explicitly so we can share it with other threads
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop_holder["loop"] = loop
    try:
        loop.run_until_complete(async_main(shutdown_event))
    finally:
        # clean up
        loop.close()


if __name__ == "__main__":
    # Use a threading.Event for cross-thread signalling (async code will poll is_set()).
    shutdown_event = threading.Event()
    loop_holder = {}

    # Start asyncio in background thread
    async_thread = threading.Thread(
        target=start_async_loop,
        args=(shutdown_event, loop_holder),
        daemon=True,
    )
    async_thread.start()

    # Wait for loop to be ready (small spin; very short)
    while "loop" not in loop_holder:
        sleep(0.01)

    try:
        from tray import run_tray
        run_tray(shutdown_event, control, loop_holder["loop"])
    except Exception as e:
        logger.warning("System tray unavailable (%s), running headless", e)
        async_thread.join()