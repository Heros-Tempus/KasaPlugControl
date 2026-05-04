import asyncio
import logging
import sys
import threading
from time import sleep, time

from control import ControlState
from normal_operation import normal_operation
from plug_functions import get_plug, get_battery_status
from config import DO_CALIBRATION_CYCLES, CALIBRATION_CYCLES
from calibration import calibration_already_done, run_calibration_cycles
from logger import setup_logging

logger = logging.getLogger(__name__)
control = ControlState()


def _wait_for_shell(timeout: int = 60) -> bool:
    """Block until the Windows taskbar shell window exists, or timeout elapses.

    The system tray lives inside Shell_TrayWnd. At login, Explorer can take
    several seconds to create it, so pystray will fail silently if we don't
    wait. Non-Windows platforms always return True immediately.
    """
    if not sys.platform.startswith("win"):
        return True
    import ctypes
    user32 = ctypes.windll.user32
    deadline = time() + timeout
    while time() < deadline:
        if user32.FindWindowW("Shell_TrayWnd", None):
            return True
        sleep(2)
    return False

async def async_main(shutdown_event: threading.Event):
    setup_logging()
    logger.info("Battery charge controller starting (normal mode)")

    plug = await get_plug()
    try:
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
    finally:
        try:
            await plug.disconnect()
        except Exception:
            logger.debug("Plug disconnect on exit")


def start_async_loop(shutdown_event: threading.Event, loop_holder: dict):
    while not shutdown_event.is_set():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop_holder["loop"] = loop
        try:
            loop.run_until_complete(async_main(shutdown_event))
        except Exception:
            if not shutdown_event.is_set():
                logger.exception("Async loop crashed — restarting in 5s")
        finally:
            loop.close()
        if not shutdown_event.is_set():
            sleep(5)


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

    if not _wait_for_shell(timeout=60):
        logger.warning("Shell_TrayWnd not found after 60s — running headless")
        async_thread.join()
    else:
        from tray import run_tray
        for attempt in range(1, 6):
            try:
                run_tray(shutdown_event, control, loop_holder)
                break  # normal exit (user clicked Quit)
            except Exception as e:
                if attempt < 5:
                    logger.warning(
                        "Tray init failed (attempt %d/5): %s — retrying in 10s", attempt, e
                    )
                    sleep(10)
                else:
                    logger.warning("Tray unavailable after 5 attempts — running headless")
                    async_thread.join()