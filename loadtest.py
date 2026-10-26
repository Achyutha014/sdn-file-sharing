"""Run N clients concurrently from one host; prints/appends per-client results as CSV.
python3 loadtest.py - host 10.0.0.100, user alice, password alice123, id h1, gives out results.csv
"""
import argparse, os, tempfile, time
from client import Client

ap = argparse.ArgumentParser()
ap.add_argument("--host", required=True); ap.add_argument("--user", default="alice")
ap.add_argument("--password", default="alice123"); ap.add_argument("--id", default="c")
ap.add_argument("--size-mb", type=float, default=10); ap.add_argument("--mode", choices=["up", "down", "both"], default="both")
ap.add_argument("--out", default=None)
a = ap.parse_args()

tmp = tempfile.mkdtemp()
name = f"{a.id}_{int(time.time()*1000)}.bin"
path = os.path.join(tmp, name)
with open(path, "wb") as fh:
    fh.write(os.urandom(int(a.size_mb * 1024 * 1024)))
rows = []
try:
    c = Client(a.host, a.user, a.password)
    if a.mode in ("up", "both"):
        s, d, _ = c.upload(path); rows.append((a.id, "upload", s, d, s * 8 / d / 1e6))
    if a.mode in ("down", "both"):
        if a.mode == "down":
            files = c.list(); name = files[0]["name"]
        s, d, _ = c.download(name, os.path.join(tmp, "dl.bin")); rows.append((a.id, "download", s, d, s * 8 / d / 1e6))
    c.close()
except Exception as e:
    rows.append((a.id, f"FAILED:{type(e).__name__}", 0, 0, 0))
for r in rows:
    line = "%s,%s,%d,%.4f,%.3f" % r
    print(line)
    if a.out:
        with open(a.out, "a") as fh: fh.write(line + "\n")
