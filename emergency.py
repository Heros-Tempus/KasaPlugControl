import logging
import subprocess
import sys
import requests
from config import PUSHOVER_APP_TOKEN, PUSHOVER_USER_KEY

logger = logging.getLogger(__name__)
def notify_emergency(title: str, message: str) -> None:
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

def hibernate_system() -> None:
    logger.critical("Battery emergency detected — hibernating system immediately")
    if sys.platform.startswith("win"):
        cmd = ["shutdown", "/h", "/f"]
    elif sys.platform == "darwin":
        cmd = ["pmset", "sleepnow"]
    else:
        cmd = ["systemctl", "hibernate"]
    subprocess.run(cmd, check=False)