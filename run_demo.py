"""D1 demo (needs: osken-manager controller.py running in another terminal):  sudo python3 run_demo.py
Shows: normal transfer -> brute-force client -> controller blocks it automatically -> others unaffected -> auto-unblock."""
import json, os, time
from mininet.log import setLogLevel
from topology import build, SERVER_IP

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCK_SECS = 20

def say(t): print("\n=== " + t, flush=True)

setLogLevel("warning")
with open(os.path.join(HERE, "policy.json"), "w") as f:
    json.dump({"blocked_ips": [], "rate_limit_kbps": {}, "auto_block_seconds": BLOCK_SECS}, f)
time.sleep(4)
net = build(4)
srv, h1, h4 = net.get("srv"), net.get("h1"), net.get("h4")
srv.cmd(f"cd {HERE} && rm -rf /tmp/sdnfs_store && python3 server.py --storage /tmp/sdnfs_store > /tmp/server.log 2>&1 &")
time.sleep(2)
try:
    say("1. Connectivity")
    print(h1.cmd(f"ping -c 2 {SERVER_IP}").strip().splitlines()[-2])
    say("2. Normal use: h1 (alice) uploads and downloads 5 MB")
    print(h1.cmd(f"cd {HERE} && python3 loadtest.py --host {SERVER_IP} --user alice --password alice123 --id h1 --size-mb 5").strip())
    say("3. Attack: h4 makes 3 wrong logins, then tries a valid login")
    print(h4.cmd(f"cd {HERE} && python3 bruteforce.py --host {SERVER_IP}").strip())
    say("4. Others unaffected: h1 transfers again while h4 is blocked")
    print(h1.cmd(f"cd {HERE} && python3 loadtest.py --host {SERVER_IP} --user alice --password alice123 --id h1 --size-mb 5").strip())
    say(f"5. Waiting {BLOCK_SECS + 5}s for the block to expire, then h4 retries a valid login")
    time.sleep(BLOCK_SECS + 5)
    print(h4.cmd(f"cd {HERE} && python3 -c \"from client import Client; c=Client('{SERVER_IP}','bob','bob123',timeout=5); print('h4 valid login: SUCCESS (access restored)'); c.close()\"").strip())
    say("Controller decisions are in dynamic_events.csv, throughput in bandwidth.csv")
finally:
    srv.cmd("pkill -f server.py")
    net.stop()
