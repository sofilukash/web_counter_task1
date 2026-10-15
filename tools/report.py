"""
Порівняльна таблиця й графік «in-memory проти disk»
"""

import os

from tools.bench import RESULTS_DIR, load_csv, median_rps

MEM_CSV = os.path.join(RESULTS_DIR, "stage1_inmemory.csv")
DISK_CSV = os.path.join(RESULTS_DIR, "stage2_disk.csv")


def compare(mem_csv: str = MEM_CSV, disk_csv: str = DISK_CSV) -> None:
    mem = median_rps(load_csv(mem_csv))
    disk = median_rps(load_csv(disk_csv))
    clients = sorted(set(mem) & set(disk))

    lines = [f"{'клієнтів':>9} {'in-memory RPS':>15} {'disk RPS':>10} {'memory/disk':>12}"]
    for c in clients:
        lines.append(f"{c:>9} {mem[c]:>15.0f} {disk[c]:>10.0f} {mem[c] / disk[c]:>11.1f}x")
    text = "\n".join(lines)
    print("\n--- Порівняння пропускної здатності ---")
    print(text)
    txt_path = os.path.join(RESULTS_DIR, "comparison.txt")
    with open(txt_path, "w") as f:
        f.write(text + "\n")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib не встановлено - графік пропущено")
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for ax, scale, title in ((axes[0], "linear", "Лінійна шкала"), (axes[1], "log", "Логарифмічна шкала")):
        for data, label, color in ((mem, "in-memory", "#1f77b4"), (disk, "disk (fsync)", "#d62728")):
            ys = [data[c] for c in clients]
            ax.plot(clients, ys, "o-", label=label, color=color)
            for x, y in zip(clients, ys):
                ax.annotate(f"{y:,.0f}", (x, y), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=8)
        ax.set_yscale(scale)
        ax.set_xticks(clients)
        ax.set_xlabel("Кількість одночасних клієнтів")
        ax.set_ylabel("Запитів на секунду (RPS)")
        ax.set_title(title)
        ax.grid(alpha=0.3)
        ax.legend()
    fig.suptitle("Web-counter: пропускна здатність залежно від навантаження і сховища")
    fig.tight_layout()
    png_path = os.path.join(RESULTS_DIR, "comparison_rps.png")
    fig.savefig(png_path, dpi=130)
    print(f"Графік: {png_path}\nТаблиця: {txt_path}")


if __name__ == "__main__":
    compare()
