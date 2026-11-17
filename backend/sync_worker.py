"""One paced writer for all students; failed batches remain in SQLite."""
import logging
import random
import threading
import time

log = logging.getLogger(__name__)


class SyncWorker:
    def __init__(self, syncer, interval=3, clock=time.monotonic,
                 jitter=lambda: random.uniform(0, 1)):
        self.syncer, self.interval, self.clock, self.jitter = syncer, interval, clock, jitter
        self.next_due = clock() + interval
        self.failures = 0
        self.lock = threading.Lock()

    def tick(self):
        if not self.lock.acquire(blocking=False):
            return
        try:
            if self.clock() < self.next_due:
                return
            try:
                self.syncer.once()
            except Exception as error:
                self.failures += 1
                delay = min(60, self.interval * 2 ** min(self.failures, 5)) + self.jitter()
                # Never log provider bodies, keys, student questions or passwords.
                status = getattr(error, 'status_code', None)
                category = f'HTTP {status}' if type(status) is int else type(error).__name__
                log.warning('試算表同步未成功，紀錄保留於資料庫；%.1f 秒後重試（%s）。',
                            delay, category)
            else:
                self.failures = 0
                delay = self.interval
            self.next_due = self.clock() + delay
        finally:
            self.lock.release()

    def run(self, stop):
        while not stop.wait(max(0, self.next_due - self.clock())):
            self.tick()
