import threading


class CancelledError(Exception):
    pass


class CancelToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self):
        self._event.set()

    @property
    def cancelled(self):
        return self._event.is_set()

    def is_cancelled(self):
        return self._event.is_set()

    def throw_if_cancelled(self):
        if self.is_cancelled():
            raise CancelledError("Operation cancelled.")
