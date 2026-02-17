import asyncio
from typing import Optional

class ControlState:
    def __init__(self):
        self.automation_enabled = True
        self.override_until: Optional[float] = None
        self._lock = asyncio.Lock()

    async def pause(self, seconds: Optional[int] = None):
        async with self._lock:
            self.automation_enabled = False
            if seconds:
                loop = asyncio.get_running_loop()
                self.override_until = loop.time() + seconds

    async def resume(self):
        async with self._lock:
            self.automation_enabled = True
            self.override_until = None

    async def should_run(self) -> bool:
        async with self._lock:
            if not self.automation_enabled:
                if self.override_until is None:
                    return False
                loop = asyncio.get_running_loop()
                if loop.time() >= self.override_until:
                    self.automation_enabled = True
                    self.override_until = None
                    return True
                return False
            return True
