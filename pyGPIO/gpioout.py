"""Wrapper around pyGPIO to behave like gpiozero.

The functionality is reduced to the minimum required for our application.

:Created:
    2025-01-20

:Author:
    | Michael Strey <strey@sarad.de>
"""

from itertools import repeat
from threading import Event, Thread

from pyGPIO.gpio import gpio, port

_THREADS = set()


class GPIOZeroError(Exception):
    "Base class for all exceptions in GPIO Zero"


class ZombieThread(GPIOZeroError, RuntimeError):
    "Error raised when a thread fails to die within a given timeout"


class GPIOThread(Thread):
    def __init__(self, target, args=(), kwargs=None, name=None):
        if kwargs is None:
            kwargs = {}
        self.stopping = Event()
        super().__init__(None, target, name, args, kwargs)
        self.daemon = True

    def start(self):
        self.stopping.clear()
        _THREADS.add(self)
        super().start()

    def stop(self, timeout=10):
        self.stopping.set()
        self.join(timeout)

    def join(self, timeout=None):
        super().join(timeout)
        if self.is_alive():
            assert timeout is not None
            # timeout can't be None here because if it was, then join()
            # wouldn't return until the thread was dead
            raise ZombieThread(f"Thread failed to die within {timeout} seconds")
        else:
            _THREADS.discard(self)


class LED:
    """
    Represents a generic output device with typical on/off behaviour.

    This class extends :class:`OutputDevice` with a :meth:`blink` method which
    uses an optional background thread to handle toggling the device state
    without further interaction.

    :type pin: int or str
    :param pin:
        The GPIO pin that the device is connected to. See :ref:`pin-numbering`
        for valid pin numbers. If this is :data:`None` a :exc:`GPIODeviceError`
        will be raised.
    """

    def __init__(self, _pin=None):
        self._blink_thread = None
        gpio.init()
        self.port = port.GPIO4
        gpio.setcfg(self.port, 1)  # gpio4 as output
        self._active_state = True
        self._inactive_state = False

    def _write(self, value):
        if value:
            gpio.output(self.port, 1)
        else:
            gpio.output(self.port, 0)

    def close(self):
        self._stop_blink()
        gpio.init()

    def on(self):
        self._stop_blink()
        self._write(True)

    def off(self):
        self._stop_blink()
        self._write(False)

    def blink(self, on_time=1, off_time=1, n=None, background=True):
        """
        Make the device turn on and off repeatedly.

        :param float on_time:
            Number of seconds on. Defaults to 1 second.

        :param float off_time:
            Number of seconds off. Defaults to 1 second.

        :type n: int or None
        :param n:
            Number of times to blink; :data:`None` (the default) means forever.

        :param bool background:
            If :data:`True` (the default), start a background thread to
            continue blinking and return immediately. If :data:`False`, only
            return when the blink is finished (warning: the default value of
            *n* will result in this method never returning).
        """
        self._stop_blink()
        self._blink_thread = GPIOThread(self._blink_device, (on_time, off_time, n))
        self._blink_thread.start()
        if not background:
            self._blink_thread.join()
            self._blink_thread = None

    def _stop_blink(self):
        if getattr(self, "_blink_thread", None):
            self._blink_thread.stop()
        self._blink_thread = None

    def _blink_device(self, on_time, off_time, n):
        iterable = repeat(0) if n is None else repeat(0, n)
        for _ in iterable:
            self._write(True)
            if self._blink_thread.stopping.wait(on_time):
                break
            self._write(False)
            if self._blink_thread.stopping.wait(off_time):
                break
