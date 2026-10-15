"""
ЕТАП 3 : Flame Graph для in-memory і disk
Для кожного режиму будуються два профілі:
    active — лише потоки, що виконуються;
    wall   — з урахуванням очікування.
Результат — у папці flamegraphs/:
    wall_disk.png, wall_memory.png, active_disk.png, active_memory.png  (+ .svg)
    *_top.txt  — таблиці функцій із відсотками
Запуск:
    python stage3_flamegraph.py                     # усе: 2 режими × 2 види
    python stage3_flamegraph.py --only disk         # лише один режим
    python stage3_flamegraph.py --kind wall         # лише wall-clock профіль
    python stage3_flamegraph.py --quick             # швидка перевірка (по 1000 запитів)
"""

import argparse

from tools.flame import profile_and_draw

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["memory", "disk"], help="профілювати лише один режим")
    ap.add_argument("--kind", choices=["active", "wall", "both"], default="both")
    ap.add_argument("--clients", type=int, default=10)
    ap.add_argument("--requests", type=int, default=10_000, help="запитів на клієнта")
    ap.add_argument("--rate", type=int, default=100, help="частота семплування py-spy, Гц")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--quick", action="store_true", help="швидка перевірка: 1000 запитів на клієнта")
    args = ap.parse_args()
    if args.quick:
        args.requests = 1000

    modes = [args.only] if args.only else ["memory", "disk"]
    kinds = ["wall", "active"] if args.kind == "both" else [args.kind]
    for mode in modes:
        for kind in kinds:
            profile_and_draw(mode, kind, args.clients, args.requests, args.rate, args.port)


if __name__ == "__main__":
    main()
