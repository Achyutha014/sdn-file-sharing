"""Run the evaluation scenarios inside Mininet (needs: sudo, ryu-manager controller.py running).
sudo python3 run_experiment.py --clients 4 --size-mb 20
Scenarios: baseline | ratelimit (h1 capped) | block (h4 blocked). Results -> results.csv
"""
import argparse, json, os, time
from mininet.log import setLogLevel
from topology import build, SERVER_IP

HERE = os.path.dirname(os.path.abspath(__file__))
POLICY = os.path.join(HERE, "policy.json")

SCENARIOS = {
    "baseline":  {"blocked_ips": [], "rate_limit_kbps": {}},
    "ratelimit": {"blocked_ips": [], "rate_limit_kbps": {"10.0.0.1": 5000}},
    "block":     {"blocked_ips": ["10.0.0.4"], "rate_limit_kbps": {}},
}


def set_policy(p):
    with open(POLICY, "w") as f:
        json.dump(p, f)
    time.sleep(4)   # controller polls every 2 s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clients", type=int, default=4); ap.add_argument("--size-mb", type=float, default=20)
    ap.add_argument("--scenarios", nargs="+", default=list(SCENARIOS))
    a = ap.parse_args()
    setLogLevel("warning")
    out = os.path.join(HERE, "results.csv")
    with open(out, "w") as f:
        f.write("scenario,n_clients,client,op,bytes,seconds,mbps\n")
    net = build(a.clients)
    srv = net.get("srv")
    srv.cmd(f"cd {HERE} && python3 server.py --storage /tmp/sdnfs_store > /tmp/server.log 2>&1 &")
    time.sleep(2)
    users = ["alice", "bob", "carol", "alice"]
    try:
        for name in a.scenarios:
            set_policy(SCENARIOS[name])
            print(f"== scenario {name}")
            tmp = f"/tmp/res_{name}.csv"
            os.system(f"rm -f {tmp}")
            hosts = [net.get(f"h{i}") for i in range(1, a.clients + 1)]
            procs = []
            for i, h in enumerate(hosts):
                u = users[i % len(users)]
                cmd = (f"cd {HERE} && timeout 120 python3 loadtest.py --host {SERVER_IP} --user {u} "
                       f"--password {u}123 --id h{i+1} --size-mb {a.size_mb} --mode both --out {tmp}")
                procs.append(h.popen(cmd, shell=True))
            for pr in procs:
                pr.wait()
            with open(tmp) as fin, open(out, "a") as fout:
                for line in fin:
                    r = line.strip().split(",")
                    fout.write(",".join([name, str(a.clients)] + r) + "\n")
    finally:
        srv.cmd("pkill -f server.py")
        net.stop()
        with open(POLICY, "w") as f:
            json.dump({"blocked_ips": [], "rate_limit_kbps": {}}, f)


if __name__ == "__main__":
    main()
