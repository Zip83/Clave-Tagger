import threading


class CancelledError(Exception):
    """CancelledError."""
    pass


class CancelToken:
    """CancelToken."""
    def __init__(self):
        """Initialize this object."""
        self._event = threading.Event()

    def cancel(self):
        """Cancel."""
        self._event.set()

    @property
    def cancelled(self):
        """Cancelled."""
        return self._event.is_set()

    def is_cancelled(self):
        """Is cancelled."""
        return self._event.is_set()

    def throw_if_cancelled(self):
        """Throw if cancelled."""
        if self.is_cancelled():
            raise CancelledError("Operation cancelled.")
