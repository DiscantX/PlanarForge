"""Load tracking and progress reporting for UI operations."""

from __future__ import annotations

import time
from typing import Callable, Optional


class LoadTracker:
    """
    Tracks timing and progress during long-running operations.
    
    Reports status updates to a callback function with elapsed time.
    Useful for measuring and displaying load progress in the UI.
    """

    def __init__(self, on_update: Optional[Callable[[str], None]] = None) -> None:
        """
        Initialize the tracker.
        
        Args:
            on_update: Optional callback that receives status messages.
                      Format: "Message... (0.00s)"
        """
        self.on_update = on_update
        self._start_time = time.perf_counter()
        self._step_times: dict[str, float] = {}

    def step(self, message: str) -> None:
        """
        Report a step in the loading process.
        
        Args:
            message: Description of what's being loaded.
        """
        elapsed = time.perf_counter() - self._start_time
        self._step_times[message] = elapsed
        status = f"{message} ({elapsed:.2f}s)"
        if self.on_update:
            self.on_update(status)

    def mark(self, message: str) -> None:
        """
        Alias for step() — mark a point in progress.
        
        Args:
            message: Description of current operation.
        """
        self.step(message)

    def elapsed(self) -> float:
        """Return total elapsed time in seconds."""
        return time.perf_counter() - self._start_time

    def get_step_times(self) -> dict[str, float]:
        """Get all recorded step times."""
        return dict(self._step_times)
