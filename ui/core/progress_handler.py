"""Reusable progress tracking for editor operations."""

from __future__ import annotations

from typing import Callable, Optional


class EditorProgressHandler:
    """
    Manages progress updates for long-running editor operations.
    
    Provides a simple callback interface that editors can wire to:
    - Async/blocking operations that report progress
    - Service load/search operations
    - Any multi-step operation that needs status display
    
    Usage in an editor:
        handler = EditorProgressHandler(toolbar.set_status)
        service.set_progress_callback(handler.on_progress)
    """

    def __init__(self, on_status_update: Callable[[str], None]) -> None:
        """
        Args:
            on_status_update: Callback that receives status messages.
                             Typically: toolbar.set_status
        """
        self.on_status_update = on_status_update

    def on_progress(self, message: str) -> None:
        """
        Report progress during an operation.
        
        Args:
            message: Status message (e.g. "Loading inventory...")
        """
        self.on_status_update(message)

    def on_complete(self, message: str) -> None:
        """
        Report operation completion.
        
        Args:
            message: Final status message
        """
        self.on_status_update(message)

    def on_error(self, message: str) -> None:
        """
        Report an error.
        
        Args:
            message: Error message
        """
        self.on_status_update(f"Error: {message}")
