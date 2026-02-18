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


def run_tray(shutdown_event, control):

    def update_icon(icon):
        mode = asyncio.run(control.get_mode())

        if mode == Mode.NORMAL:
            icon.icon = create_icon("green")
        elif mode == Mode.PAUSED:
            icon.icon = create_icon("yellow")
        elif mode == Mode.FORCE_ON:
            icon.icon = create_icon("blue")
        elif mode == Mode.FORCE_OFF:
            icon.icon = create_icon("red")

    def set_mode(mode, duration=None):
        asyncio.run(control.set_mode(mode, duration))
        update_icon(icon)

    def force_on(icon, item):
        set_mode(Mode.FORCE_ON)

    def force_on_2h(icon, item):
        set_mode(Mode.FORCE_ON, 7200)

    def force_off(icon, item):
        set_mode(Mode.FORCE_OFF)

    def force_off_2h(icon, item):
        set_mode(Mode.FORCE_OFF, 7200)

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
        "Battery Charge Controller",
        menu=pystray.Menu(
            item("Force ON", force_on),
            item("Force ON (2 hours)", force_on_2h),
            item("Force OFF", force_off),
            item("Force OFF (2 hours)", force_off_2h),
            pystray.Menu.SEPARATOR,
            item("Pause Automation", pause),
            item("Pause (2 hours)", pause_2h),
            item("Resume Normal Mode", resume),
            pystray.Menu.SEPARATOR,
            item("Quit", quit_app),
        ),
    )

    icon.run()
