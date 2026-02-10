import logging
from logging.handlers import RotatingFileHandler
from config import LOG_FILE

def setup_logging() -> None:
    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=25 * 1024,   # 25 KB
        backupCount=1
    )
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)
