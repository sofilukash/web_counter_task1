"""
Автотести ядра
Запуск:    python -m unittest -v tests.test_counters
Перевіряємо головні вимоги:
  * немає lost update при багатьох потоках (memory і disk);
  * disk-лічильник зберігає значення у файлі й переживає перезапуск;
  * два процеси не можуть одночасно відкрити один файл лічильника;
  * HTTP-ендпоінти /inc і /count працюють і при паралельних клієнтах.
"""

import http.client
import os
import sys
import tempfile
import threading
import unittest

from app.counters import DiskCounter, MemoryCounter
from app.server import CounterServer, make_handler

def hammer(counter, threads: int, per_thread: int) -> None:
    # Багато потоків одночасно викликають inc()

    def work():
        for _ in range(per_thread):
            counter.inc()

    ts = [threading.Thread(target=work) for _ in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()


class CounterTests(unittest.TestCase):
    def setUp(self):
        self._old_interval = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)

    def tearDown(self):
        sys.setswitchinterval(self._old_interval)

    def test_memory_no_lost_update(self):
        c = MemoryCounter()
        hammer(c, threads=20, per_thread=10_000)
        self.assertEqual(c.get(), 200_000)

    def test_disk_no_lost_update(self):
        with tempfile.TemporaryDirectory() as d:
            c = DiskCounter(os.path.join(d, "c.dat"), fsync=False)
            hammer(c, threads=20, per_thread=500)
            self.assertEqual(c.get(), 10_000)
            c.close()

    def test_disk_value_is_really_in_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.dat")
            c = DiskCounter(path)  # з fsync
            for _ in range(7):
                c.inc()
            with open(path, "rb") as f:
                self.assertEqual(int(f.read()), 7)
            c.close()

    def test_disk_survives_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.dat")
            c = DiskCounter(path, fsync=False)
            hammer(c, threads=4, per_thread=250)
            c.close()
            c2 = DiskCounter(path)
            self.assertEqual(c2.get(), 1000)
            c2.inc()
            self.assertEqual(c2.get(), 1001)
            c2.close()

    @unittest.skipIf(os.name == "nt", "flock на Windows працює інакше")
    def test_disk_file_is_locked_against_second_opener(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "c.dat")
            c = DiskCounter(path, fsync=False)
            with self.assertRaises(RuntimeError):
                DiskCounter(path, fsync=False)
            c.close()

    def test_reset(self):
        for c in (MemoryCounter(),):
            c.inc()
            c.reset()
            self.assertEqual(c.get(), 0)


class HttpTests(unittest.TestCase):
    # Піднімаємо справжній сервер у потоці й заходимо на нього з кількох клієнтів

    def _check(self, counter):
        server = CounterServer(("127.0.0.1", 0), make_handler(counter))
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            def client():
                conn = http.client.HTTPConnection("127.0.0.1", port)
                for _ in range(200):
                    conn.request("GET", "/inc")
                    r = conn.getresponse()
                    r.read()
                    self.assertEqual(r.status, 200)
                conn.close()

            ts = [threading.Thread(target=client) for _ in range(5)]
            [t.start() for t in ts]
            [t.join() for t in ts]
            conn = http.client.HTTPConnection("127.0.0.1", port)
            conn.request("GET", "/count")
            self.assertEqual(int(conn.getresponse().read()), 1000)
            conn.request("GET", "/nothing")
            r = conn.getresponse()
            r.read()
            self.assertEqual(r.status, 404)
            conn.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_http_memory(self):
        self._check(MemoryCounter())

    def test_http_disk(self):
        with tempfile.TemporaryDirectory() as d:
            c = DiskCounter(os.path.join(d, "c.dat"), fsync=False)
            self._check(c)
            c.close()


if __name__ == "__main__":
    unittest.main()
