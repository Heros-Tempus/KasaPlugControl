
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