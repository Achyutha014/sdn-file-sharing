"""Shared protocol helpers. Wire format: one JSON header line (UTF-8, '\n'-terminated),
followed by raw bytes when the header carries a 'size' field."""
import json

PORT = 5000
CHUNK = 64 * 1024


def send_msg(sock, obj):
    sock.sendall((json.dumps(obj) + "\n").encode())


def recv_line(f):
    line = f.readline(65536)
    if not line:
        raise ConnectionError("connection closed")
    return json.loads(line.decode())


def send_file_bytes(sock, path):
    with open(path, "rb") as fh:
        while True:
            buf = fh.read(CHUNK)
            if not buf:
                break
            sock.sendall(buf)


def recv_exact_to_file(f, path, size):

    import hashlib
    h = hashlib.sha256()
    left = size
    with open(path, "wb") as out:
        while left > 0:
            buf = f.read(min(CHUNK, left))
            if not buf:
                raise ConnectionError("truncated transfer")
            out.write(buf)
            h.update(buf)
            left -= len(buf)
    return h.hexdigest()

EVENT_FILE = "/tmp/sdnfs_events.jsonl"


def emit_event(**ev):
    import json, time
    ev["time"] = time.time()
    with open(EVENT_FILE, "a") as f:
        f.write(json.dumps(ev) + "\n")
