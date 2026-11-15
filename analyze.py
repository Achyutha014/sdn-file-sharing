"""Summarise results.csv (+ optional bandwidth.csv from the controller) and plot."""
import csv, collections, statistics as st, sys

rows = list(csv.DictReader(open("results.csv")))
by = collections.defaultdict(list)
for r in rows:
    if not r["op"].startswith("FAILED"):
        by[(r["scenario"], r["op"])].append(r)

def jain(x):
    return (sum(x) ** 2) / (len(x) * sum(v * v for v in x)) if x and sum(x) else 0

print(f"{'scenario':10} {'op':9} {'ok':>3} {'fail':>4} {'avg Mbps':>9} {'min':>7} {'max':>7} {'Jain':>6}")
summary = {}
for (sc, op), rs in sorted(by.items()):
    ok = [float(r["mbps"]) for r in rs]
    print(f"{sc:10} {op:9} {len(ok):>3} {'':>4} {st.mean(ok):9.2f} {min(ok):7.2f} {max(ok):7.2f} {jain(ok):6.3f}")
    summary[(sc, op)] = ok
for r in rows:
    if r["op"].startswith("FAILED"):
        print("FAILED:", r["scenario"], r["client"], r["op"])

try:
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    scs = sorted({k[0] for k in by})
    fig, ax = plt.subplots(figsize=(7, 4))
    for i, op in enumerate(["upload", "download"]):
        ax.bar([j + i * 0.35 for j in range(len(scs))], [st.mean(summary[(s, op)]) if summary.get((s, op)) else 0 for s in scs], 0.35, label=op)
    ax.set_xticks([j + 0.175 for j in range(len(scs))]); ax.set_xticklabels(scs)
    ax.set_ylabel("mean per-client throughput (Mbit/s)"); ax.legend(); fig.tight_layout()
    fig.savefig("throughput.png", dpi=150); print("saved throughput.png")
except ImportError:
    print("matplotlib not installed; skipping plot")
