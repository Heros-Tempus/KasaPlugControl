import logging
from logging.handlers import RotatingFileHandler
from config import LOG_FILE, LOG_FILE_BACKUP_SIZE, LOG_FILE_BACKUP_COUNT

def setup_logging() -> None:
    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes = LOG_FILE_BACKUP_SIZE,
        backupCount=LOG_FILE_BACKUP_COUNT
    )
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Clear existing handlers before adding the new one. The root logger is
    # a process-level singleton, so without this each loop restart would
    # attach an additional handler and produce duplicate log entries.
    root.handlers.clear()
    root.addHandler(handler)
