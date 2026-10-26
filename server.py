"""Multithreaded TCP file-sharing server with authentication and metadata (SQLite).
Usage: python3 server.py-host 0.0.0.0, port 5000
"""
import argparse, hashlib, os, secrets, socket, sqlite3, threading, time, logging
from common import PORT, send_msg, recv_line, send_file_bytes, recv_exact_to_file, emit_event

log = logging.getLogger("server")
USERS = {"alice": "alice123", "bob": "bob123", "carol": "carol123"}  # demo credentials (stored hashed below)
FAIL_LIMIT, FAIL_WINDOW = 3, 60          # 3 bad logins within 60 s from one IP -> tell the SDN controller
_fails, _fails_lock = {}, threading.Lock()
USER_HASH = {u: hashlib.sha256(p.encode()).hexdigest() for u, p in USERS.items()}


class MetaStore:
    """Thread-safe SQLite metadata store (one lock, short-lived connections)."""
    def __init__(self, path):
        self.path, self.lock = path, threading.Lock()
        with self._conn() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS files(
                name TEXT PRIMARY KEY, owner TEXT, size INTEGER, sha256 TEXT, uploaded_at REAL)""")

    def _conn(self):
        return sqlite3.connect(self.path)

    def put(self, name, owner, size, digest):
        with self.lock, self._conn() as c:
            c.execute("REPLACE INTO files VALUES(?,?,?,?,?)", (name, owner, size, digest, time.time()))

    def get(self, name):
        with self.lock, self._conn() as c:
            return c.execute("SELECT name,owner,size,sha256,uploaded_at FROM files WHERE name=?", (name,)).fetchone()

    def list(self):
        with self.lock, self._conn() as c:
            return c.execute("SELECT name,owner,size,sha256,uploaded_at FROM files ORDER BY name").fetchall()


def note_failed_login(ip):
    now = time.time()
    with _fails_lock:
        hist = [t for t in _fails.get(ip, []) if now - t < FAIL_WINDOW] + [now]
        _fails[ip] = hist
        trip = len(hist) >= FAIL_LIMIT
        if trip:
            _fails[ip] = []
    if trip:
        log.warning("%d failed logins from %s -> notifying SDN controller", FAIL_LIMIT, ip)
        emit_event(type="auth_fail_threshold", ip=ip, count=FAIL_LIMIT)


def safe_name(n):
    return os.path.basename(n) == n and n not in ("", ".", "..")


def handle(conn, addr, storage, meta):
    f = conn.makefile("rb")
    user = None
    log.info("connect %s", addr)
    try:
        while True:
            try:
                req = recv_line(f)
            except ConnectionError:
                break
            cmd = req.get("cmd")
            if cmd == "AUTH":
                u, p = req.get("user"), req.get("password", "")
                if u in USER_HASH and secrets.compare_digest(USER_HASH[u], hashlib.sha256(p.encode()).hexdigest()):
                    user = u
                    send_msg(conn, {"ok": True, "token": secrets.token_hex(8)})
                else:
                    send_msg(conn, {"ok": False, "error": "bad credentials"})
                    note_failed_login(addr[0])
                continue
            if user is None:
                send_msg(conn, {"ok": False, "error": "authenticate first"})
                continue
            if cmd == "LIST":
                rows = meta.list()
                send_msg(conn, {"ok": True, "files": [dict(name=r[0], owner=r[1], size=r[2], sha256=r[3], uploaded_at=r[4]) for r in rows]})
            elif cmd == "UPLOAD":
                name, size = req.get("name", ""), int(req.get("size", -1))
                if not safe_name(name) or size < 0:
                    send_msg(conn, {"ok": False, "error": "bad name/size"})
                    continue
                existing = meta.get(name)
                if existing and existing[1] != user:
                    send_msg(conn, {"ok": False, "error": "file owned by another user"})
                    continue
                send_msg(conn, {"ok": True, "ready": True})
                tmp = os.path.join(storage, f".{name}.{threading.get_ident()}.part")
                digest = recv_exact_to_file(f, tmp, size)
                os.replace(tmp, os.path.join(storage, name))
                meta.put(name, user, size, digest)
                send_msg(conn, {"ok": True, "sha256": digest})
                log.info("%s uploaded %s (%d B)", user, name, size)
            elif cmd == "DOWNLOAD":
                name = req.get("name", "")
                row = meta.get(name) if safe_name(name) else None
                if not row:
                    send_msg(conn, {"ok": False, "error": "no such file"})
                    continue
                send_msg(conn, {"ok": True, "size": row[2], "sha256": row[3]})
                send_file_bytes(conn, os.path.join(storage, name))
                log.info("%s downloaded %s", user, name)
            elif cmd == "QUIT":
                break
            else:
                send_msg(conn, {"ok": False, "error": "unknown command"})
    except Exception as e:
        log.exception("error with %s: %s", addr, e)
    finally:
        f.close(); conn.close()
        log.info("disconnect %s", addr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--storage", default="./storage")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    os.makedirs(a.storage, exist_ok=True)
    meta = MetaStore(os.path.join(a.storage, "meta.db"))
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((a.host, a.port)); s.listen(128)
    log.info("listening on %s:%d", a.host, a.port)
    while True:
        conn, addr = s.accept()
        threading.Thread(target=handle, args=(conn, addr, a.storage, meta), daemon=True).start()


if __name__ == "__main__":
    main()
