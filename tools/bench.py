"""
Автоматичний запуск серії вимірювань: сам піднімає сервер, запускає клієнтів, зупиняє сервер
Використовується скриптами stage1_inmemory.py та stage2_disk.py
"""

import csv
import os
import subprocess
import sys
import time

from tools.loadgen import format_run, http_get, run_load

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(ROOT, "results")

CLIENTS = (1, 2, 5, 10)
CSV_FIELDS = ["mode", "clients", "run", "requests_per_client", "total_requests", "wall_seconds", "rps",
              "avg_ms", "p50_ms", "p99_ms", "errors", "final_count", "expected_count", "file_value", "ok"]


def start_server(mode: str, port: int, counter_file: str = None) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "app.server", "--mode", mode, "--port", str(port)]
    if mode == "disk":
        cmd += ["--file", counter_file]
    os.makedirs(RESULTS_DIR, exist_ok=True)
    log = open(os.path.join(RESULTS_DIR, f"server_{mode}.log"), "w")
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    wait_ready(proc, port)
    return proc


def wait_ready(proc: subprocess.Popen, port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("Сервер не запустився (див. results/server_*.log)")
        try:
            http_get("127.0.0.1", port, "/count")
            return
        except OSError:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("Сервер не відповів за відведений час")


def stop_server(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def read_counter_file(path: str) -> int:
    # Читаємо файл лічильника напряму з диска, повз сервер
    with open(path, "rb") as f:
        return int(f.read())


def run_matrix(mode: str, requests: int = 10_000, repeats: int = 3, port: int = 8080,
               clients_list=CLIENTS) -> list:
    # Повертає список замірів
    counter_file = os.path.join(RESULTS_DIR, "counter.dat")
    if mode == "disk" and os.path.exists(counter_file):
        os.remove(counter_file)

    print(f"\n=== Режим: {mode} | {requests} запитів на клієнта | повторів: {repeats} ===")
    server = start_server(mode, port, counter_file)
    rows = []
    try:
        for clients in clients_list:
            for run in range(1, repeats + 1):
                r = run_load(f"http://127.0.0.1:{port}", clients, requests)
                r.update(mode=mode, run=run, file_value="")
                if mode == "disk":
                    # значення, яке лежить у файлі, має збігатися з тим, що віддає /count
                    r["file_value"] = read_counter_file(counter_file)
                    r["ok"] = r["ok"] and r["file_value"] == r["expected_count"]
                print(format_run(f"{mode}#{run}", r))
                rows.append(r)
                if not r["ok"]:
                    raise RuntimeError("Лічильник показує неправильне значення — оновлення губляться!")
    finally:
        stop_server(server)
    return rows


def save_csv(rows: list, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def load_csv(path: str) -> list:
    num = ("clients", "run", "requests_per_client", "total_requests", "errors", "final_count", "expected_count")
    flt = ("wall_seconds", "rps", "avg_ms", "p50_ms", "p99_ms")
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            for k in num:
                r[k] = int(r[k])
            for k in flt:
                r[k] = float(r[k])
            rows.append(r)
    return rows


def summarize(rows: list) -> list:
    # По одному рядку на кількість клієнтів: беремо медіанний за RPS замір
    out = []
    for clients in sorted({r["clients"] for r in rows}):
        group = sorted((r for r in rows if r["clients"] == clients), key=lambda r: r["rps"])
        med = dict(group[len(group) // 2])
        med["rps_min"], med["rps_max"] = group[0]["rps"], group[-1]["rps"]
        med["runs"] = len(group)
        out.append(med)
    return out


def print_summary(title: str, rows: list) -> None:
    print(f"\n--- {title}: медіана за повторами ---")
    print(f"{'клієнтів':>9} {'запитів':>9} {'час, с':>9} {'RPS':>10} {'RPS min..max':>16} {'avg, мс':>8} {'p99, мс':>8}  count")
    for s in summarize(rows):
        print(f"{s['clients']:>9} {s['total_requests']:>9} {s['wall_seconds']:>9.2f} {s['rps']:>10.0f} "
              f"{s['rps_min']:>7.0f}..{s['rps_max']:<7.0f} {s['avg_ms']:>8.3f} {s['p99_ms']:>8.2f}  "
              f"{s['final_count']}/{s['expected_count']}")


def median_rps(rows: list) -> dict:
    return {s["clients"]: s["rps"] for s in summarize(rows)}

