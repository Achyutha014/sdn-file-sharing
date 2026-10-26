"""File-sharing client (library + CLI).
CLI: python3 client.py-host 10.0.0.100, user alice, p alice123 and upload file.bin
"""
import argparse, hashlib, os, socket, time
from common import PORT, send_msg, recv_line, send_file_bytes, recv_exact_to_file


class Client:
    def __init__(self, host, user, password, port=PORT, timeout=60):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.f = self.sock.makefile("rb")
        send_msg(self.sock, {"cmd": "AUTH", "user": user, "password": password})
        r = recv_line(self.f)
        if not r.get("ok"):
            raise PermissionError(r.get("error"))

    def list(self):
        send_msg(self.sock, {"cmd": "LIST"})
        return recv_line(self.f)["files"]

    def upload(self, path):
        name, size = os.path.basename(path), os.path.getsize(path)
        send_msg(self.sock, {"cmd": "UPLOAD", "name": name, "size": size})
        r = recv_line(self.f)
        if not r.get("ok"):
            raise RuntimeError(r.get("error"))
        t = time.time()
        send_file_bytes(self.sock, path)
        r = recv_line(self.f)
        return size, time.time() - t, r["sha256"]

    def download(self, name, dest):
        send_msg(self.sock, {"cmd": "DOWNLOAD", "name": name})
        r = recv_line(self.f)
        if not r.get("ok"):
            raise RuntimeError(r.get("error"))
        t = time.time()
        digest = recv_exact_to_file(self.f, dest, r["size"])
        if digest != r["sha256"]:
            raise IOError("checksum mismatch")
        return r["size"], time.time() - t, digest

    def close(self):
        try: send_msg(self.sock, {"cmd": "QUIT"})
        finally: self.f.close(); self.sock.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True); ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("-u", "--user", required=True); ap.add_argument("-p", "--password", required=True)
    ap.add_argument("action", choices=["list", "upload", "download"])
    ap.add_argument("arg", nargs="?"); ap.add_argument("dest", nargs="?", default=".")
    a = ap.parse_args()
    c = Client(a.host, a.user, a.password, a.port)
    if a.action == "list":
        for m in c.list(): print(f"{m['name']:30} {m['size']:>12} B  owner={m['owner']}")
    elif a.action == "upload":
        s, d, _ = c.upload(a.arg); print(f"uploaded {s} B in {d:.3f}s ({s*8/d/1e6:.1f} Mbit/s)")
    else:
        dest = os.path.join(a.dest, a.arg) if os.path.isdir(a.dest) else a.dest
        s, d, _ = c.download(a.arg, dest); print(f"downloaded {s} B in {d:.3f}s ({s*8/d/1e6:.1f} Mbit/s)")
    c.close()
