"""
Збір профілю сервера (py-spy) і автоматична побудова Flame Graph
"""

import os
import re
import shutil
import signal
import subprocess
import sys
import time
import zlib

from tools.bench import RESULTS_DIR, ROOT, start_server, stop_server
from tools.loadgen import run_load

FLAME_DIR = os.path.join(ROOT, "flamegraphs")
# ----------------------------------------------------------------------------- py-spy
def find_pyspy() -> str:
    exe = shutil.which("py-spy")
    if exe is None:
        cand = os.path.join(os.path.dirname(sys.executable), "py-spy")
        exe = cand if os.path.exists(cand) else None
    if exe is None:
        raise RuntimeError("py-spy не знайдено")
    return exe


def record(mode: str, kind: str, clients: int, requests: int, rate: int, port: int) -> str:
    # Запускає сервер + py-spy + навантаження
    os.makedirs(FLAME_DIR, exist_ok=True)
    raw = os.path.join(FLAME_DIR, f"{kind}_{mode}.raw")
    if os.path.exists(raw):
        os.remove(raw)
    counter_file = os.path.join(RESULTS_DIR, "counter_profile.dat")
    if mode == "disk" and os.path.exists(counter_file):
        os.remove(counter_file)

    server = start_server(mode, port, counter_file)
    spy_log = open(os.path.join(FLAME_DIR, f"pyspy_{kind}_{mode}.log"), "w")
    cmd = [find_pyspy(), "record", "-p", str(server.pid), "-r", str(rate),
           "--nonblocking",
           "--function",
           "-f", "raw", "-o", raw]
    if kind == "wall":
        cmd.append("--idle")
    spy = subprocess.Popen(cmd, stdout=spy_log, stderr=subprocess.STDOUT)
    try:
        time.sleep(2.0)
        if spy.poll() is not None:
            spy_log.flush()
            tail = open(spy_log.name).read()[-600:]
            raise RuntimeError("py-spy не зміг під'єднатись до сервера:\n" + tail + "\nПідказка: запустіть через sudo")
        print(f"  навантаження: {clients} клієнтів × {requests} запитів ...", flush=True)
        res = run_load(f"http://127.0.0.1:{port}", clients, requests)
        print(f"  готово: {res['rps']:.0f} RPS (під профілювальником), count={res['final_count']}"
              f" {'OK' if res['ok'] else 'ПОМИЛКА'}")
    finally:
        if spy.poll() is None:
            spy.send_signal(signal.SIGINT)
            try:
                spy.wait(timeout=60)
            except subprocess.TimeoutExpired:
                spy.kill()
        spy_log.close()
        stop_server(server)
    if not os.path.exists(raw) or os.path.getsize(raw) == 0:
        raise RuntimeError(f"py-spy не створив {raw}; див. {spy_log.name}")
    return raw


# ----------------------------------------------------------------------------- розбір стеків
def _func(frame: str) -> str:
    return re.sub(r":\d+\)", ")", frame)


def _name(frame: str) -> str:
    return re.sub(r" \(.*\)$", "", frame)


def _is_idle(frames: list) -> bool:
    names = [_name(f) for f in frames]
    if "serve_forever" in names:
        return True
    return names[-2:] == ["handle_one_request", "readinto"]


def parse_raw(raw_path: str):
    stacks, dropped = [], 0
    with open(raw_path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            stack, count = line.rsplit(" ", 1)
            frames = [_func(fr) for fr in stack.split(";")]
            if not stack.strip() or _is_idle(frames):
                dropped += int(count)
            else:
                stacks.append((tuple(frames), int(count)))
    return stacks, dropped


# ----------------------------------------------------------------------------- таблиця функцій
_BOILERPLATE = {"_bootstrap", "_bootstrap_inner", "run", "process_request_thread", "finish_request",
                "__init__", "handle"}


def summarize(stacks: list, top: int = 12) -> str:
    total = sum(n for _, n in stacks)
    inclusive, self_time = {}, {}
    for frames, n in stacks:
        for fn in set(_func(f) for f in frames):
            if _name(fn) not in _BOILERPLATE:
                inclusive[fn] = inclusive.get(fn, 0) + n
        leaf = frames[-1]
        self_time[leaf] = self_time.get(leaf, 0) + n

    def block(title, data):
        lines = [title]
        for fn, n in sorted(data.items(), key=lambda kv: -kv[1])[:top]:
            lines.append(f"  {n / total * 100:6.1f}%  {fn}")
        return "\n".join(lines)

    return (f"Усього семплів (без простою за конструкцією): {total}\n\n"
            + block("ВКЛЮЧНО (частка семплів, де функція є в стеку; службові кадри потоків/socketserver не показано):", inclusive)
            + "\n\n"
            + block("ВЛАСНИЙ ЧАС (частка семплів, де функція - кінець стеку - «де час витрачається насправді»):", self_time))

# ----------------------------------------------------------------------------- малювання
class _Node:
    __slots__ = ("name", "total", "children")

    def __init__(self, name):
        self.name, self.total, self.children = name, 0, {}


def _build_tree(stacks: list) -> _Node:
    root = _Node("all")
    for frames, n in stacks:
        root.total += n
        node = root
        for fr in frames:
            node = node.children.setdefault(fr, _Node(fr))
            node.total += n
    return root


def _color(name: str):
    h = zlib.crc32(name.encode())
    return ((205 + h % 50) / 255, (60 + (h >> 8) % 170) / 255, (20 + (h >> 16) % 40) / 255)


def draw(stacks: list, title: str, subtitle: str, png_path: str, svg_path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    matplotlib.rcParams["svg.fonttype"] = "none"
    root = _build_tree(stacks)

    MIN_W = 0.0015

    def depth(node):
        kids = [c for c in node.children.values() if c.total / root.total >= MIN_W]
        return 1 + max((depth(c) for c in kids), default=0)

    levels = depth(root)
    fig_w, dpi, fs = 18.0, 100, 9
    row_h = 0.30
    fig, ax = plt.subplots(figsize=(fig_w, row_h * levels + 1.4), dpi=dpi)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, levels)
    ax.axis("off")
    char_px = fs * dpi / 72 * 0.60
    ax_px = fig_w * dpi * 0.96

    stack = [(root, 0.0, 0)]
    while stack:
        node, x0, level = stack.pop()
        w = node.total / root.total
        if w < MIN_W:
            continue
        ax.add_patch(Rectangle((x0, level), w, 0.94, facecolor=_color(node.name), edgecolor="white", linewidth=0.6))
        label = f"{node.name} ({w * 100:.1f}%)"
        fit = int(w * ax_px / char_px)
        if fit >= 4:
            if len(label) > fit:
                label = label[: max(fit - 1, 1)] + "…"
            ax.text(x0 + 0.002, level + 0.47, label, fontsize=fs, va="center", ha="left", clip_on=True)
        x = x0
        for child in sorted(node.children.values(), key=lambda c: c.name):  # як у flamegraph.pl: за алфавітом
            stack.append((child, x, level + 1))
            x += child.total / root.total

    fig.suptitle(title, fontsize=13, y=0.99)
    fig.text(0.5, 0.94, subtitle, ha="center", fontsize=9, color="#555")
    fig.subplots_adjust(left=0.02, right=0.98, bottom=0.01, top=0.90)
    fig.savefig(png_path)
    fig.savefig(svg_path)
    plt.close(fig)

# ----------------------------------------------------------------------------- головна функція
def profile_and_draw(mode: str, kind: str, clients: int = 10, requests: int = 10_000,
                     rate: int = 100, port: int = 8080) -> None:
    label = {"active": "тільки активні потоки (≈CPU)", "wall": "wall-clock: разом з очікуванням"}[kind]
    print(f"\n=== Flame Graph: {mode} / {kind} — {label} ===")
    raw = record(mode, kind, clients, requests, rate, port)
    stacks, dropped = parse_raw(raw)
    if not stacks:
        raise RuntimeError("У профілі немає корисних семплів")
    if sum(n for _, n in stacks) < 300:
        print("  УВАГА: семплів мало, відсотки будуть неточні - збільште --requests (за замовчуванням 10000)")

    base = os.path.join(FLAME_DIR, f"{kind}_{mode}")
    with open(base + ".folded", "w") as f:
        for frames, n in stacks:
            f.write(";".join(frames) + f" {n}\n")

    total = sum(n for _, n in stacks)
    title = f"{'In-memory' if mode == 'memory' else 'Disk'} counter — {kind} flame graph"
    subtitle = (f"{clients} клієнтів × {requests} запитів · py-spy {rate} Гц · "
                f"{total} семплів (відкинуто {dropped} простою за конструкцією)")
    draw(stacks, title, subtitle, base + ".png", base + ".svg")

    summary = summarize(stacks)
    with open(base + "_top.txt", "w") as f:
        f.write(f"{title}\n{subtitle}\n\n{summary}\n")
    print(summary)
    print(f"\n  Графік:  {base}.png  (та .svg)\n  Таблиця: {base}_top.txt")
