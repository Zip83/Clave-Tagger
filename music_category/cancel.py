import threading


class CancelledError(Exception):
    """Provide CancelledError behavior."""
    pass


class CancelToken:
    """Provide CancelToken behavior."""
    def __init__(self):
        """Initialize this object."""
        self._event = threading.Event()

    def cancel(self):
        """Provide cancel behavior."""
        self._event.set()

    @property
    def cancelled(self):
        """Provide cancelled behavior."""
        return self._event.is_set()

    def is_cancelled(self):
        """Provide is cancelled behavior."""
        return self._event.is_set()

    def throw_if_cancelled(self):
        """Provide throw if cancelled behavior."""
        if self.is_cancelled():
            raise CancelledError("Operation cancelled.")
