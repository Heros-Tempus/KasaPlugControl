import asyncio
from enum import Enum, auto
from typing import Optional


class Mode(Enum):
    NORMAL = auto()
    PAUSED = auto()
    FORCE_ON = auto()
    FORCE_OFF = auto()


class ControlState:
    def __init__(self):
        self.mode = Mode.NORMAL
        self.until: Optional[float] = None
        self._lock = asyncio.Lock()

    async def set_mode(self, mode: Mode, duration_seconds: Optional[int] = None):
        async with self._lock:
            self.mode = mode
            if duration_seconds:
                loop = asyncio.get_running_loop()
                self.until = loop.time() + duration_seconds
            else:
                self.until = None

    async def get_mode(self):
        async with self._lock:
            # Auto-expire timed overrides
            if self.until is not None:
                loop = asyncio.get_running_loop()
                if loop.time() >= self.until:
                    self.mode = Mode.NORMAL
                    self.until = None
                    
            remaining = None
            if self.until is not None:
                loop = asyncio.get_running_loop()
                remaining = max(0, int(self.until - loop.time()))

            return self.mode, remaining
