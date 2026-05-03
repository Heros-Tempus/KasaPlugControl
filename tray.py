import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
from control import Mode
import asyncio
import logging

ICON_SIZE = 64
logger = logging.getLogger(__name__)

def create_icon(color):
    image = Image.new("RGB", (ICON_SIZE, ICON_SIZE), (30, 30, 30))
    draw = ImageDraw.Draw(image)
    draw.ellipse((16, 16, 48, 48), fill=color)
    return image


def format_remaining(seconds):
    if seconds is None:
        return ""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f" ({hours}h {minutes}m remaining)"


def run_tray(shutdown_event, control, loop_holder):
    """
    shutdown_event: threading.Event (shared)
    control: ControlState instance (async methods)
    loop_holder: dict with key "loop" pointing to the current asyncio event loop;
                 updated in place when the loop restarts after a crash
    """

    def run_async(coro, timeout=10):
        """
        Submit coroutine to the current loop and return result (or raise).
        Reads loop_holder["loop"] on every call so it picks up restarted loops.
        """
        loop = loop_holder.get("loop")
        if loop is None or loop.is_closed():
            coro.close()
            raise RuntimeError("Async loop is not running")
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout)

    def update_visuals(icon):
        try:
            mode, remaining = run_async(control.get_mode())
        except Exception as e:
            logger.exception("Failed to fetch mode for tray visuals: %s", e)
            # keep previous visuals if update fails
            return

        color, text = "", ""
        if mode == Mode.NORMAL:
            color = "green"
            text = "Normal Automation"
        elif mode == Mode.PAUSED:
            color = "yellow"
            text = "Paused"
        elif mode == Mode.FORCE_ON:
            color = "blue"
            text = "Force ON"
        elif mode == Mode.FORCE_OFF:
            color = "red"
            text = "Force OFF"

        icon.icon = create_icon(color)
        icon.title = "Battery Controller\n" + text + format_remaining(remaining)

    def set_mode(mode, duration=None):
        try:
            run_async(control.set_mode(mode, duration))
            update_visuals(icon)
        except Exception as e:
            logger.exception("Failed to set mode from tray: %s", e)

    # safe wrappers so exceptions don't escape to pystray
    def safe_call(fn):
        def wrapper(icon, item):
            try:
                fn(icon, item)
            except Exception:
                logger.exception("Tray callback failed")
        return wrapper

    def force_on(icon, item):
        set_mode(Mode.FORCE_ON)

    def force_on_2h(icon, item):
        set_mode(Mode.FORCE_ON, 7200)

    def force_off(icon, item):
        set_mode(Mode.FORCE_OFF)

    def pause(icon, item):
        set_mode(Mode.PAUSED)

    def pause_2h(icon, item):
        set_mode(Mode.PAUSED, 7200)

    def resume(icon, item):
        set_mode(Mode.NORMAL)

    def quit_app(icon, item):
        try:
            shutdown_event.set()  # threading.Event
        except Exception:
            logger.exception("Failed to set shutdown event from tray")
        finally:
            # stop tray UI
            try:
                icon.stop()
            except Exception:
                logger.exception("Failed to stop tray icon")

    icon = pystray.Icon(
        "BatteryController",
        create_icon("green"),
        "Battery Controller",
        menu=pystray.Menu(
            item("Force ON", safe_call(force_on)),
            item("Force ON (2 hours)", safe_call(force_on_2h)),
            item("Force OFF", safe_call(force_off)),
            pystray.Menu.SEPARATOR,
            item("Pause Automation", safe_call(pause)),
            item("Pause (2 hours)", safe_call(pause_2h)),
            item("Resume Normal Mode", safe_call(resume)),
            pystray.Menu.SEPARATOR,
            item("Quit", safe_call(quit_app)),
        ),
    )

    # initial update (defensive)
    try:
        update_visuals(icon)
    except Exception:
        logger.exception("Initial tray update failed")

    icon.run()
