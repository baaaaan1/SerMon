import threading
import unittest
from collections import deque
from unittest.mock import patch

import serial
from PySide6.QtCore import Qt

from serial_engine import SerialManager


class FakeSerial:
    def __init__(
        self, *, data=b"", open_error=None, dtr_error=None, write_error=None,
        block_open=False, block_dtr=False, block_read=False,
        read_error=None, close_releases_read=True,
    ):
        self.port = None
        self.baudrate = 0
        self.is_open = False
        self.settings = {}
        self.open_error = open_error
        self.dtr_error = dtr_error
        self.write_error = write_error
        self.read_error = read_error
        self.poll_error = None
        self.close_releases_read = close_releases_read
        self.close_count = 0
        self.writes = []
        self.dtr_values = []
        self._data = bytearray(data)
        self._dtr = True
        self._lock = threading.Lock()
        self.open_started = threading.Event()
        self.dtr_started = threading.Event()
        self.read_started = threading.Event()
        self.read_finished = threading.Event()
        self.closed = threading.Event()
        self.allow_open = threading.Event()
        self.allow_dtr = threading.Event()
        self.allow_read = threading.Event()
        if not block_open:
            self.allow_open.set()
        if not block_dtr:
            self.allow_dtr.set()
        if not block_read:
            self.allow_read.set()

    def open(self):
        self.open_started.set()
        if not self.allow_open.wait(3):
            raise serial.SerialException("test open timed out")
        # Also model a driver that acquires a handle before open() fails.
        self.is_open = True
        if self.open_error is not None:
            raise self.open_error

    @property
    def dtr(self):
        return self._dtr

    @dtr.setter
    def dtr(self, value):
        self.dtr_started.set()
        if not self.allow_dtr.wait(3):
            raise serial.SerialException("test DTR timed out")
        if self.dtr_error is not None:
            raise self.dtr_error
        self._dtr = value
        self.dtr_values.append(value)

    @property
    def in_waiting(self):
        with self._lock:
            if self.poll_error is not None:
                raise self.poll_error
            if not self.is_open:
                raise serial.SerialException("port closed")
            return len(self._data)

    def read(self, size):
        self.read_started.set()
        try:
            if not self.allow_read.wait(3):
                raise serial.SerialException("test read timed out")
            if self.read_error is not None:
                raise self.read_error
            with self._lock:
                data = bytes(self._data[:size])
                del self._data[:size]
                return data
        finally:
            self.read_finished.set()

    def lose_link(self):
        with self._lock:
            self.poll_error = serial.SerialException("unplugged")

    def write(self, data):
        if self.write_error is not None:
            raise self.write_error
        self.writes.append(data)
        return len(data)

    def close(self):
        self.close_count += 1
        self.is_open = False
        if self.close_releases_read:
            self.allow_read.set()
        self.closed.set()

    def release(self):
        self.allow_open.set()
        self.allow_dtr.set()
        self.allow_read.set()


class SerialFactory:
    def __init__(self):
        self.pending = deque()
        self.fakes = []
        self.calls = []
        self.unexpected_calls = 0
        self.condition = threading.Condition()

    def queue(self, *fakes):
        self.pending.extend(fakes)
        self.fakes.extend(fakes)

    def __call__(self, **settings):
        with self.condition:
            if not self.pending:
                self.unexpected_calls += 1
                self.condition.notify_all()
                raise serial.SerialException("unexpected open attempt")
            fake = self.pending.popleft()
            fake.settings = settings
            fake.port = settings["port"]
            fake.baudrate = settings["baudrate"]
            self.calls.append(fake)
            self.condition.notify_all()
            return fake

    def wait_for_calls(self, count, timeout=2):
        with self.condition:
            return self.condition.wait_for(
                lambda: len(self.calls) + self.unexpected_calls >= count, timeout
            )


class SignalLog:
    def __init__(self, manager):
        self.condition = threading.Condition()
        self.events = []
        # No application/event loop is needed, and no QCoreApplication can
        # interfere with other suites that need to create a QApplication.
        for name in ("connected", "disconnected", "data_received", "status_changed"):
            getattr(manager, name).connect(
                lambda value, name=name: self.record(name, value),
                Qt.ConnectionType.DirectConnection,
            )

    def record(self, name, value):
        with self.condition:
            self.events.append((name, value))
            self.condition.notify_all()

    def values(self, name):
        with self.condition:
            return [value for event, value in self.events if event == name]

    def wait(self, name, value=None, count=1):
        with self.condition:
            return self.condition.wait_for(
                lambda: sum(
                    event == name and (value is None or item == value)
                    for event, item in self.events
                ) >= count,
                2,
            )


class SerialManagerTests(unittest.TestCase):
    def setUp(self):
        self.factory = SerialFactory()
        self.serial_patch = patch("serial_engine.serial.Serial", self.factory)
        self.serial_patch.start()
        self.manager = SerialManager()
        self.manager._reconnect_delay = 0.02
        self.log = SignalLog(self.manager)

    def tearDown(self):
        try:
            for fake in self.factory.fakes:
                fake.release()
            thread = self.manager._thread
            self.manager.stop()
            if thread is not None:
                self.assertFalse(thread.is_alive(), "serial worker leaked")
            self.assertTrue(all(not fake.is_open for fake in self.factory.calls))
            self.assertEqual(self.factory.unexpected_calls, 0)
        finally:
            self.serial_patch.stop()

    def wait_signal(self, name, value=None, count=1):
        self.assertTrue(
            self.log.wait(name, value, count),
            f"Missing {name}({value!r}), events: {self.log.events!r}",
        )

    def assert_no_more_opens(self):
        self.assertFalse(self.factory.wait_for_calls(len(self.factory.calls) + 1, 0.08))

    def test_enabling_retries_at_launch_does_not_connect(self):
        self.manager.configure("COM7", 57600)
        self.manager.set_auto_reconnect(True)

        self.assertTrue(self.manager.auto_reconnect)
        self.assertFalse(self.manager.connection_requested)
        self.assertIsNone(self.manager._thread)
        self.assert_no_more_opens()

    def test_initial_open_failure_retries_and_succeeds(self):
        failed = FakeSerial(open_error=serial.SerialException("busy"))
        opened = FakeSerial(data=b"ready")
        self.factory.queue(failed, opened)
        self.manager.set_auto_reconnect(True)
        self.manager.connect("COM7", 57600)
        self.wait_signal("data_received", b"ready")

        self.assertEqual(failed.close_count, 1)
        self.assertFalse(failed.is_open)
        self.assertTrue(self.manager.is_open)
        self.assertTrue(self.manager.connection_requested)
        self.assertEqual(self.log.values("connected"), ["COM7"])
        self.assertEqual((self.manager.port, self.manager.baudrate), ("COM7", 57600))
        self.assertEqual(self.manager.rx_count, 5)
        self.assertEqual(self.manager.tx_count, 0)
        self.assertEqual(opened.settings["port"], None)
        self.assertEqual(opened.settings["timeout"], 0.05)
        self.assertEqual(opened.settings["write_timeout"], 2.0)

    def test_read_loss_reconnects_and_resets_counters(self):
        first, second = FakeSerial(data=b"old"), FakeSerial(data=b"new data")
        self.factory.queue(first, second)
        self.manager.set_auto_reconnect(True)
        self.manager.connect("COM7")
        self.wait_signal("data_received", b"old")
        self.assertEqual(self.manager.write(b"sent"), 4)
        self.assertEqual(self.manager.tx_count, 4)

        first.lose_link()
        self.wait_signal("data_received", b"new data")

        self.assertEqual(self.log.values("disconnected"), ["unplugged"])
        self.assertEqual(self.log.values("connected"), ["COM7", "COM7"])
        self.assertEqual(first.close_count, 1)
        self.assertEqual(self.manager.rx_count, 8)
        self.assertEqual(self.manager.tx_count, 0)

    def test_manual_disconnect_cancels_backoff_and_forgets_request(self):
        self.factory.queue(FakeSerial(open_error=serial.SerialException("busy")))
        self.manager._reconnect_delay = 10
        self.manager.set_auto_reconnect(True)
        self.manager.connect("COM7")
        self.wait_signal("status_changed", "Retrying in 10s...")
        worker = self.manager._thread

        self.manager.disconnect()
        self.manager.set_auto_reconnect(False)
        self.manager.set_auto_reconnect(True)

        self.assertFalse(self.manager.connection_requested)
        self.assertEqual(self.log.values("disconnected"), ["user"])
        self.assertIs(self.manager._thread, worker)
        self.assertTrue(worker.is_alive())
        self.assert_no_more_opens()

    def test_manual_disconnect_during_open_discards_late_success(self):
        opening = FakeSerial(block_open=True)
        self.factory.queue(opening)
        self.manager.set_auto_reconnect(True)
        self.manager.connect("COM7")
        self.assertTrue(opening.open_started.wait(2))

        self.manager.disconnect()
        self.assertFalse(self.manager.connection_requested)
        self.assertFalse(self.manager.is_open)
        opening.allow_open.set()
        self.assertTrue(opening.closed.wait(2))

        self.assertEqual(self.log.values("connected"), [])
        self.assertEqual(self.log.values("disconnected"), ["user"])
        self.assertEqual(opening.close_count, 1)
        self.assert_no_more_opens()

    def test_canceled_open_failure_does_not_emit_stale_status(self):
        opening = FakeSerial(
            block_open=True, open_error=serial.SerialException("late failure")
        )
        self.factory.queue(opening)
        self.manager.connect("COM7")
        self.assertTrue(opening.open_started.wait(2))

        self.manager.disconnect()
        opening.allow_open.set()
        self.assertTrue(opening.closed.wait(2))
        self.assert_no_more_opens()

        self.assertEqual(self.log.values("status_changed"), ["Connecting...", "Disconnected"])
        self.assertEqual(self.log.values("disconnected"), ["user"])

    def test_manual_disconnect_during_dtr_discards_unpublished_handle(self):
        opening = FakeSerial(block_dtr=True)
        self.factory.queue(opening)
        self.manager.connect("COM7")
        self.assertTrue(opening.dtr_started.wait(2))
        self.assertFalse(self.manager.is_open)

        self.manager.disconnect()
        opening.allow_dtr.set()
        self.assertTrue(opening.closed.wait(2))

        self.assertEqual(self.log.values("connected"), [])
        self.assertEqual(self.log.values("disconnected"), ["user"])
        self.assertFalse(self.manager.connection_requested)

    def test_fast_disconnect_connect_supersedes_inflight_open(self):
        first = FakeSerial(block_open=True)
        second = FakeSerial(data=b"new")
        self.factory.queue(first, second)
        self.manager.connect("COM1", 9600)
        self.assertTrue(first.open_started.wait(2))
        worker = self.manager._thread

        self.manager.disconnect()
        self.manager.connect("COM2", 19200)
        self.assertTrue(self.manager.connection_requested)
        self.assertIs(self.manager._thread, worker)
        first.allow_open.set()
        self.wait_signal("data_received", b"new")

        self.assertEqual(self.log.values("connected"), ["COM2"])
        self.assertEqual(self.log.values("disconnected"), ["user"])
        self.assertEqual(first.close_count, 1)
        self.assertEqual((self.manager.port, self.manager.baudrate), ("COM2", 19200))

    def test_fast_disconnect_connect_reuses_idle_worker(self):
        self.factory.queue(FakeSerial(data=b"old"), FakeSerial(data=b"new"))
        self.manager.connect("COM7")
        self.wait_signal("data_received", b"old")
        worker = self.manager._thread

        self.manager.disconnect()
        self.manager.connect("COM7")
        self.wait_signal("data_received", b"new")

        self.assertIs(self.manager._thread, worker)
        self.assertTrue(self.manager.is_open)
        self.assertEqual(self.manager.rx_count, 3)

    def test_stale_read_data_does_not_reach_new_connection(self):
        first = FakeSerial(data=b"stale", block_read=True, close_releases_read=False)
        self.factory.queue(first, FakeSerial(data=b"new"))
        self.manager.connect("COM1")
        self.assertTrue(first.read_started.wait(2))

        self.manager.disconnect()
        self.manager.connect("COM2")
        first.allow_read.set()
        self.wait_signal("data_received", b"new")

        self.assertEqual(self.log.values("data_received"), [b"new"])
        self.assertEqual(self.log.values("disconnected"), ["user"])
        self.assertEqual(self.manager.rx_count, 3)

    def test_stale_read_failure_does_not_disconnect_new_request(self):
        first = FakeSerial(
            data=b"old", block_read=True, close_releases_read=False,
            read_error=serial.SerialException("late read error"),
        )
        self.factory.queue(first, FakeSerial(data=b"new"))
        self.manager.set_auto_reconnect(True)
        self.manager.connect("COM1")
        self.assertTrue(first.read_started.wait(2))

        self.manager.disconnect()
        self.manager.connect("COM2")
        first.allow_read.set()
        self.wait_signal("data_received", b"new")

        self.assertEqual(self.log.values("disconnected"), ["user"])
        self.assertEqual(self.log.values("connected"), ["COM1", "COM2"])
        self.assertFalse(any("late read error" in s for s in self.log.values("status_changed")))

    def test_disabling_retries_cancels_backoff_and_enabling_resumes_it(self):
        self.factory.queue(
            FakeSerial(open_error=serial.SerialException("busy")), FakeSerial()
        )
        self.manager._reconnect_delay = 10
        self.manager.set_auto_reconnect(True)
        self.manager.connect("COM7")
        self.wait_signal("status_changed", "Retrying in 10s...")

        self.manager.set_auto_reconnect(False)
        self.assertFalse(self.manager.connection_requested)
        self.assert_no_more_opens()
        self.manager.set_auto_reconnect(True)
        self.wait_signal("connected", "COM7")

        self.assertTrue(self.manager.connection_requested)

    def test_disabling_retries_cancels_an_inflight_retry(self):
        retry = FakeSerial(block_open=True)
        self.factory.queue(
            FakeSerial(open_error=serial.SerialException("busy")), retry, FakeSerial()
        )
        self.manager.set_auto_reconnect(True)
        self.manager.connect("COM7")
        self.assertTrue(retry.open_started.wait(2))

        self.manager.set_auto_reconnect(False)
        self.assertFalse(self.manager.connection_requested)
        retry.allow_open.set()
        self.assertTrue(retry.closed.wait(2))
        self.assert_no_more_opens()
        self.assertEqual(self.log.values("connected"), [])
        self.manager.set_auto_reconnect(True)
        self.wait_signal("connected", "COM7")

    def test_disabling_reconnect_preserves_live_link_but_not_lost_request(self):
        first = FakeSerial()
        self.factory.queue(first, FakeSerial())
        self.manager.set_auto_reconnect(True)
        self.manager.connect("COM7")
        self.wait_signal("connected", "COM7")

        self.manager.set_auto_reconnect(False)
        self.assertTrue(self.manager.is_open)
        self.assertTrue(self.manager.connection_requested)
        first.lose_link()
        self.wait_signal("status_changed", "Disconnected: unplugged")
        self.assertFalse(self.manager.connection_requested)
        self.assert_no_more_opens()
        self.manager.set_auto_reconnect(True)
        self.wait_signal("connected", "COM7", count=2)

    def test_disabling_retries_during_initial_open_keeps_explicit_attempt(self):
        opening = FakeSerial(block_open=True)
        self.factory.queue(opening)
        self.manager.set_auto_reconnect(True)
        self.manager.connect("COM7")
        self.assertTrue(opening.open_started.wait(2))

        self.manager.set_auto_reconnect(False)
        self.assertTrue(self.manager.connection_requested)
        opening.allow_open.set()
        self.wait_signal("connected", "COM7")

        self.assertTrue(self.manager.is_open)
        self.assertFalse(self.manager.auto_reconnect)

    def test_enabling_retries_resumes_initial_failure_without_connect(self):
        self.factory.queue(
            FakeSerial(open_error=serial.SerialException("busy")), FakeSerial()
        )
        self.manager.connect("COM7")
        self.wait_signal("status_changed", "Connection failed")

        self.assertFalse(self.manager.connection_requested)
        self.assert_no_more_opens()
        self.manager.set_auto_reconnect(True)
        self.wait_signal("connected", "COM7")

        self.assertTrue(self.manager.connection_requested)

    def test_manual_disconnect_forgets_a_failed_request(self):
        self.factory.queue(FakeSerial(open_error=serial.SerialException("busy")))
        self.manager.connect("COM7")
        self.wait_signal("status_changed", "Connection failed")

        self.manager.disconnect()
        self.manager.set_auto_reconnect(True)

        self.assertFalse(self.manager.connection_requested)
        self.assert_no_more_opens()

    def test_dtr_failure_closes_open_handle_and_can_retry(self):
        failed = FakeSerial(dtr_error=serial.SerialException("DTR failed"))
        opened = FakeSerial()
        self.factory.queue(failed, opened)
        self.manager.set_dtr(False)
        self.manager.connect("COM7")
        self.wait_signal("status_changed", "Connection failed")

        self.assertEqual(failed.close_count, 1)
        self.assertFalse(failed.is_open)
        self.assertFalse(self.manager.is_open)
        self.assertEqual(self.log.values("connected"), [])
        self.manager.set_auto_reconnect(True)
        self.wait_signal("connected", "COM7")
        self.assertFalse(opened.dtr)

    def test_dtr_changed_during_open_is_applied_before_publication(self):
        opening = FakeSerial(block_dtr=True)
        self.factory.queue(opening)
        self.manager.connect("COM7")
        self.assertTrue(opening.dtr_started.wait(2))

        self.manager.set_dtr(False)
        opening.allow_dtr.set()
        self.wait_signal("connected", "COM7")

        self.assertEqual(opening.dtr_values, [True, False])
        self.assertFalse(self.manager.dtr)
        self.assertFalse(opening.dtr)
        self.manager.set_dtr(True)
        self.assertTrue(opening.dtr)

    def test_write_failure_closes_handle_and_reconnects_once(self):
        first = FakeSerial(write_error=serial.SerialException("write failed"))
        second = FakeSerial()
        self.factory.queue(first, second)
        self.manager.set_auto_reconnect(True)
        self.manager.connect("COM7")
        self.wait_signal("connected", "COM7")

        self.assertEqual(self.manager.write(b"lost"), -1)
        self.wait_signal("connected", "COM7", count=2)

        self.assertEqual(first.close_count, 1)
        self.assertEqual(self.log.values("disconnected"), ["TX error: write failed"])
        self.assertEqual(self.manager.tx_count, 0)
        self.assertEqual(self.manager.write(b"sent"), 4)
        self.assertEqual(second.writes, [b"sent"])
        self.assertEqual(self.manager.tx_count, 4)

    def test_write_failure_without_retries_waits_for_opt_in(self):
        first = FakeSerial(write_error=serial.SerialTimeoutException("write timed out"))
        self.factory.queue(first, FakeSerial())
        self.manager.connect("COM7")
        self.wait_signal("connected", "COM7")

        self.assertEqual(self.manager.write(b"lost"), -1)
        self.assertFalse(self.manager.is_open)
        self.assertFalse(self.manager.connection_requested)
        self.assertEqual(first.close_count, 1)
        self.assertEqual(self.manager.write(b"offline"), -1)
        self.assert_no_more_opens()
        self.manager.set_auto_reconnect(True)
        self.wait_signal("connected", "COM7", count=2)

    def test_stop_interrupts_backoff_and_worker_can_restart(self):
        self.factory.queue(
            FakeSerial(open_error=serial.SerialException("busy")), FakeSerial()
        )
        self.manager._reconnect_delay = 10
        self.manager.set_auto_reconnect(True)
        self.manager.connect("COM7")
        self.wait_signal("status_changed", "Retrying in 10s...")
        worker = self.manager._thread

        self.manager.stop()

        self.assertFalse(worker.is_alive())
        self.assertFalse(self.manager.connection_requested)
        self.manager.connect("COM7")
        self.wait_signal("connected", "COM7")
        self.assertIsNot(self.manager._thread, worker)

    def test_stop_during_open_closes_late_handle_without_events(self):
        opening = FakeSerial(block_open=True)
        self.factory.queue(opening)
        self.manager.connect("COM7")
        self.assertTrue(opening.open_started.wait(2))
        worker = self.manager._thread
        stopper = threading.Thread(target=self.manager.stop)
        stopper.start()
        try:
            with self.manager._condition:
                self.assertTrue(self.manager._condition.wait_for(self.manager._stop.is_set, 2))
            opening.allow_open.set()
        finally:
            opening.release()
            stopper.join(3)

        self.assertFalse(stopper.is_alive())
        self.assertFalse(worker.is_alive())
        self.assertEqual(opening.close_count, 1)
        self.assertEqual(self.log.values("connected"), [])
        self.assertEqual(self.log.values("disconnected"), [])
        self.assertFalse(self.manager.connection_requested)

    def test_status_properties_use_live_settings_and_are_read_only(self):
        self.factory.queue(FakeSerial())
        self.manager.connect("COM7", 19200)
        self.wait_signal("connected", "COM7")
        self.manager.configure("COM9", 57600)

        self.assertEqual((self.manager.port, self.manager.baudrate), ("COM7", 19200))
        for name in ("connection_requested", "request_id", "port", "baudrate"):
            with self.assertRaises(AttributeError):
                setattr(self.manager, name, None)
        self.manager.disconnect()
        self.assertEqual((self.manager.port, self.manager.baudrate), ("COM9", 57600))


if __name__ == "__main__":
    unittest.main()
