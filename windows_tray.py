import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
from control import Mode
import asyncio

ICON_SIZE = 64


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


def run_tray(shutdown_event, control):

    def update_visuals(icon):
        mode, remaining = asyncio.run(control.get_mode())
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
        asyncio.run(control.set_mode(mode, duration))
        update_visuals(icon)

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
        shutdown_event.set()
        icon.stop()

    icon = pystray.Icon(
        "BatteryController",
        create_icon("green"),
        "Battery Controller",
        menu=pystray.Menu(
            item("Force ON", force_on),
            item("Force ON (2 hours)", force_on_2h),
            item("Force OFF", force_off),
            pystray.Menu.SEPARATOR,
            item("Pause Automation", pause),
            item("Pause (2 hours)", pause_2h),
            item("Resume Normal Mode", resume),
            pystray.Menu.SEPARATOR,
            item("Quit", quit_app),
        ),
    )

    update_visuals(icon)
    icon.run()
