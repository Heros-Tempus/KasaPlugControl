from time import time
from normal_operation import get_battery_status
import asyncio
import logging
import subprocess
import requests
from config import PUSHOVER_APP_TOKEN, PUSHOVER_USER_KEY

logger = logging.getLogger(__name__)
def notify_emergency(title: str, message: str):
    try:
        requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": PUSHOVER_APP_TOKEN,
                "user": PUSHOVER_USER_KEY,
                "title": title,
                "message": message,
                "priority": 1,  # high priority
            },
            timeout=5,
        )
    except Exception as e:
        logger.error("Failed to send Pushover alert: %s", e)

def hibernate_system():
    logger.critical("Battery emergency detected — hibernating system immediately")
    subprocess.run(
        ["shutdown", "/h", "/f"],
        check=False
    )

async def verify_charging_after_plug_on(timeout=5):
    start = time()
    while time() - start < timeout:
        _, power_plugged = get_battery_status()
        if power_plugged:
            logging.info("Charging confirmed after plug ON")
            return True
        await asyncio.sleep(0.5)
    logging.critical("Plug ON but laptop did NOT start charging within %ds", timeout)
    notify_emergency(
        "Charging Failure",
        "Smart plug turned ON but laptop did not start charging within 5 seconds. "
        "Check cable, adapter, or outlet immediately.",
    )
    return False