"""Async/threaded loader for long-running operations."""

from __future__ import annotations

import threading
from typing import Callable, Optional, TypeVar, Generic

T = TypeVar("T")


class AsyncLoader(Generic[T]):
    """
    Executes a long-running operation in a background thread while
    allowing the main UI thread to update a spinner/progress indicator.
    
    Thread-safe callback system for progress updates.
    """

    def __init__(
        self,
        operation: Callable[..., T],
        on_progress: Optional[Callable[[str], None]] = None,
        on_complete: Optional[Callable[[T], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ):
        """
        Args:
            operation: Callable that performs the long operation. 
                      May take no args or (on_progress) callback as arg.
            on_progress: Called with status messages from background thread.
            on_complete: Called with result when operation succeeds.
            on_error: Called with exception if operation fails.
        """
        self.operation = operation
        self.on_progress = on_progress
        self.on_complete = on_complete
        self.on_error = on_error
        
        self._thread: Optional[threading.Thread] = None
        self._result: Optional[T] = None
        self._exception: Optional[Exception] = None
        self._is_running = False
        self._lock = threading.Lock()

    def start(self, *args, **kwargs) -> None:
        """Start the background operation."""
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
            self._result = None
            self._exception = None
        
        self._thread = threading.Thread(
            target=self._run,
            args=args,
            kwargs=kwargs,
            daemon=False,
        )
        self._thread.start()

    def _run(self, *args, **kwargs) -> None:
        """Background thread execution."""
        try:
            # Try passing the progress callback to the operation
            try:
                result = self.operation(self.on_progress, *args, **kwargs)
            except TypeError:
                # Operation doesn't accept progress callback
                result = self.operation(*args, **kwargs)
            
            with self._lock:
                self._result = result
            
            if self.on_complete:
                self.on_complete(result)
        except Exception as exc:
            with self._lock:
                self._exception = exc
            
            if self.on_error:
                self.on_error(exc)
        finally:
            with self._lock:
                self._is_running = False

    def is_running(self) -> bool:
        """Check if operation is still running."""
        with self._lock:
            return self._is_running

    def is_complete(self) -> bool:
        """Check if operation completed successfully."""
        with self._lock:
            return self._result is not None and self._exception is None

    def get_result(self) -> Optional[T]:
        """Get the result (blocks until complete or returns None if not done)."""
        if self._thread:
            self._thread.join(timeout=0.1)
        with self._lock:
            return self._result

    def wait(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for operation to complete.
        
        Returns True if completed, False if timed out.
        """
        if self._thread:
            self._thread.join(timeout=timeout)
        with self._lock:
            return not self._is_running
