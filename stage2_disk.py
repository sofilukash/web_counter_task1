"""
ЕТАП 2 : лічильник на диску
Скрипт:
    1. запускає сервер у режимі disk, ганяє ті самі 1/2/5/10 клієнтів × 10K запитів;
    2. після кожного заміру перевіряє двічі: /count == очікуваному 1 число, яке
       лежить у файлі counter.dat (читаємо його напряму, повз сервер), теж == очікуваному;
    3. зберігає results/stage2_disk.csv;
    4. якщо вже є результати Етапу 1 — будує порівняльну таблицю і графік
       (results/comparison.txt, results/comparison_rps.png).
Запуск:
    python stage2_disk.py             # повний прогін
    python stage2_disk.py --quick     # швидка перевірка (по 1000 запитів, 1 повтор)
"""
import argparse
import os

from tools import report
from tools.bench import RESULTS_DIR, print_summary, run_matrix, save_csv


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--requests", type=int, default=10_000, help="запитів на клієнта (за замовчуванням 10000)")
    ap.add_argument("--repeats", type=int, default=3, help="скільки разів повторити кожен замір (береться медіана)")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--quick", action="store_true", help="швидка перевірка: 1000 запитів, 1 повтор")
    args = ap.parse_args()
    if args.quick:
        args.requests, args.repeats = 1000, 1

    rows = run_matrix("disk", requests=args.requests, repeats=args.repeats, port=args.port)
    print_summary("disk (fsync)", rows)
    out = f"{RESULTS_DIR}/stage2_disk.csv"
    save_csv(rows, out)
    print(f"\nЗбережено: {out}")

    if os.path.exists(report.MEM_CSV):
        report.compare()
    else:
        print("\n(Порівняння не побудовано: спершу запустіть  python stage1_inmemory.py)")


if __name__ == "__main__":
    main()
