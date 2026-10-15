"""
Два варіанти лічильника з однаковим інтерфейсом: inc() / get() / reset() / close()
1. MemoryCounter — число в оперативній пам'яті (1-ша частина завдання)
2. DiskCounter   — число у файлі на диску (2-га частина завдання)
"""

import os
import threading

try:  # Linux / macOS
    import fcntl
except ImportError:  # Windows
    fcntl = None
try:  # Windows
    import msvcrt
except ImportError:  # Linux / macOS
    msvcrt = None

_HAS_PREAD = hasattr(os, "pread") and hasattr(os, "pwrite")  # Linux/macOS


class MemoryCounter: #Лічильник у пам'яті

    def __init__(self):
        self._lock = threading.Lock()
        self._value = 0

    def inc(self) -> int:
        with self._lock:
            self._value += 1
            return self._value

    def get(self) -> int:
        with self._lock:
            return self._value

    def reset(self) -> None:
        with self._lock:
            self._value = 0

    def close(self) -> None:
        pass


class DiskCounter: #Лічильник у файлі з записом на диск

    RECORD_LEN = 21  # 20 цифр + символ нового рядка

    def __init__(self, path: str, fsync: bool = True):
        self._lock = threading.Lock()
        self._fsync = fsync  # False для експериментів
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)  # O_BINARY - для Windows
        self._fd = os.open(path, flags, 0o644)
        try:
            self._lock_file()
        except OSError as e:
            os.close(self._fd)
            raise RuntimeError(f"Файл {path} уже використовує інший процес") from e
        if os.fstat(self._fd).st_size < self.RECORD_LEN:
            self._write(0)

    # внутрішні методи: викликаємо коли тримаємо self._lock
    def _lock_file(self) -> None:
        if fcntl is not None:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        elif msvcrt is not None:
            os.lseek(self._fd, 0, os.SEEK_SET)
            msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)

    def _read(self) -> int:
        if _HAS_PREAD:  # POSIX: читання за позицією, не чіпає спільний курсор файлу
            data = os.pread(self._fd, self.RECORD_LEN, 0)
        else:  # Windows: переміщуємо курсор вручну
            os.lseek(self._fd, 0, os.SEEK_SET)
            data = os.read(self._fd, self.RECORD_LEN)
        try:
            return int(data)
        except ValueError as e:
            raise RuntimeError(f"Файл лічильника пошкоджено: {data!r}") from e

    def _write(self, value: int) -> None:
        record = b"%020d\n" % value
        if _HAS_PREAD:
            os.pwrite(self._fd, record, 0)
        else:
            os.lseek(self._fd, 0, os.SEEK_SET)
            os.write(self._fd, record)
        if self._fsync:
            os.fsync(self._fd)  # гарантія запису на диск

    # публічний інтерфейс
    def inc(self) -> int:
        with self._lock:
            value = self._read() + 1
            self._write(value)
            return value

    def get(self) -> int:
        with self._lock:  # щоб не прочитати значення під час чужого запису
            return self._read()

    def reset(self) -> None:
        with self._lock:
            self._write(0)

    def close(self) -> None:
        os.close(self._fd)
