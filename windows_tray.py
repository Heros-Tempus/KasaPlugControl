import pystray
from pystray import MenuItem as item
from PIL import Image


def create_image():
    return Image.new("RGB", (64, 64), (50, 50, 50))


def run_tray(shutdown_event):

    def quit_app(icon, menu_item):
        shutdown_event.set()
        icon.stop()

    icon = pystray.Icon(
        "BatteryController",
        create_image(),
        "Battery Charge Controller",
        menu=pystray.Menu(
            item("Quit", quit_app),
        ),
    )

    icon.run()
