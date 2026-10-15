"""
Демонстрація: навіщо потрібен Lock
Запуск: python -m tests.demo_lost_update
"""

import os
import sys
import tempfile
import threading

from app.counters import DiskCounter

class UnsafeDiskCounter(DiskCounter):

    def inc(self):
        try:
            value = self._read() + 1
            self._write(value)
            return value
        except RuntimeError:
            return 0


def run(cls, threads=8, per_thread=500):
    with tempfile.TemporaryDirectory() as d:
        c = cls(os.path.join(d, "c.dat"), fsync=False)
        ts = [threading.Thread(target=lambda: [c.inc() for _ in range(per_thread)]) for _ in range(threads)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        got = c.get()
        c.close()
    return got, threads * per_thread


if __name__ == "__main__":
    sys.setswitchinterval(1e-6)
    for cls in (UnsafeDiskCounter, DiskCounter):
        got, expected = run(cls)
        print(f"{cls.__name__:<18} очікували={expected}  отримали={got}  втрачено={expected - got}")
