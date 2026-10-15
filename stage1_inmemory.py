"""ЕТАП 1 : лічильник в оперативній пм'яті
Скрипт:
    1. запускає сервер у режимі memory;
    2. ганяє клієнтів: 1 -> 10K, 2 -> 20K, 5 -> 50K, 10 -> 100K запитів сумарно
       (кожен клієнт робить по 10 000 послідовних /inc; клієнти стартують одночасно);
    3. після кожного заміру перевіряє, що /count == очікуваному (немає lost update);
    4. друкує таблицю RPS і зберігає results/stage1_inmemory.csv.
Запуск:
    python stage1_inmemory.py             # повний прогін
    python stage1_inmemory.py --quick     # швидка перевірка (по 1000 запитів, 1 повтор)
"""

import argparse

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

    rows = run_matrix("memory", requests=args.requests, repeats=args.repeats, port=args.port)
    print_summary("in-memory", rows)
    out = f"{RESULTS_DIR}/stage1_inmemory.csv"
    save_csv(rows, out)
    print(f"\nЗбережено: {out}")


if __name__ == "__main__":
    main()
