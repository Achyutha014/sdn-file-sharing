# Concurrent File Sharing System with SDN Control

Project 14 – SDN Socket Programming Mini Project (Computer Networks)

Multiple clients upload and download files over TCP through an OpenFlow 1.3 switch in Mininet. An os-ken SDN controller monitors the traffic and applies access policies. The server reports repeated failed logins to the controller, which blocks the offending client at the switch.

## Team and contributions

| Member | SRN | Files |
|---|---|---|
| Achyutha N Kumar | PES1UG25CS020 | `controller.py`, `server.py`, `common.py`, `run_controller.py`, `policy.json`, `run_experiment.py`, `analyze.py`, README, design document |
| Abheek P | PES1UG25CS011 | `topology.py`, `client.py`, `run_demo.py`, 'diag.py' |
| Akash Shetty | PES1UG25CS044 | `loadtest.py`, `bruteforce.py`, architecture diagram |

## Architecture

```
 Clients h1-h4 (10.0.0.1-4)          File server srv (10.0.0.100:5000)
   client.py / loadtest.py   <--TCP-->  s1 (Open vSwitch, OpenFlow 1.3)  <--TCP-->  server.py
   bruteforce.py (attacker)                      ^
                                                 | OpenFlow 1.3 (port 6653)
                                      SDN controller (os-ken)
                                      policy.json, bandwidth.csv, dynamic_events.csv
```

Server to controller path: the server appends failed-login events to `/tmp/sdnfs_events.jsonl` and the controller reads that file. This works because Mininet hosts share the filesystem with the controller.

## Repository files

| File | Purpose |
|---|---|
| `server.py` | Multithreaded TCP file server (auth, list, upload, download, SQLite metadata) |
| `client.py` | Command-line client (`list`, `upload`, `download`) |
| `common.py` | Shared protocol helpers and constants |
| `controller.py` | os-ken OpenFlow 1.3 controller: learning switch, drop rules, meters, bandwidth monitoring |
| `run_controller.py` | Starts the controller on current Python (no `osken-manager` command) |
| `policy.json` | Blocked IPs, per-host rate limits (kbps), `auto_block_seconds` |
| `topology.py` | Mininet topology: one switch, server and N clients, 100 Mbit/s links |
| `run_demo.py` | D1 demo: normal use, brute-force attack, block, recovery |
| `loadtest.py` | Upload/download load generator, reports Mbit/s |
| `bruteforce.py` | Wrong-login attacker used in the demo |
| `run_experiment.py` | D2 experiment: concurrent transfers under baseline, ratelimit and block scenarios, writes `results.csv` |
| `analyze.py` | Summarises `results.csv` (mean, min, max Mbit/s, Jain's fairness index) and saves `throughput.png` |
| `results_n1.csv`, `results_n2.csv`, `results_n4.csv` | Experiment results for 1, 2 and 4 clients |
| `throughput_n*.png` | Throughput charts per client count |
| `bandwidth.csv`, `dynamic_events.csv` | Controller outputs: flow bandwidth and block/unblock decisions |
| `screenshots/` | Terminal screenshots of the runs |

## Protocol (TCP, port 5000)

- Each request is one JSON line: `AUTH`, `LIST`, `UPLOAD`, `DOWNLOAD`, `QUIT`.
- Transfers send a `size` followed by exactly that many raw bytes, because TCP has no message boundaries.
- One thread per client. A client must `AUTH` before any other command.
- Passwords are stored as SHA-256 hashes. File names are sanitised. Only a file's owner can overwrite it.
- Metadata (name, owner, size, SHA-256, upload time) is kept in SQLite. Uploads go to a temporary file and are renamed when complete.
- The client verifies the SHA-256 after every download.
- Demo users: `alice/alice123`, `bob/bob123`, `carol/carol123`.

## SDN behaviour

- **Learning switch:** a table-miss rule (priority 0) sends unknown packets to the controller. It installs flows with a 30 s idle timeout (priority 10 for IPs, 5 for MACs).
- **Access policy:** priority-200 drop rules block IPs listed in `policy.json`. The file is reloaded when it changes.
- **Rate limiting:** a host listed in `rate_limit_kbps` is limited by an OpenFlow meter with a drop band, applied to flows where that host is source or destination.
- **Bandwidth monitoring:** flow stats are polled every 2 s and written to `bandwidth.csv`.
- **Socket to SDN integration:** after 3 failed logins from one IP within 60 s the server writes an event. The controller reads the event file every 0.5 s, installs drop rules for that IP, and removes them after `auto_block_seconds` (20 s in the demo). Every decision is logged in `dynamic_events.csv`.

## Environment

Ubuntu 26.04 (ARM64) VM, Mininet, Open vSwitch, os-ken 4.1.1 (apt package), Python 3.

```
sudo apt update
sudo apt install -y mininet python3-os-ken git
git clone https://github.com/Achyutha014/sdn-file-sharing.git
cd sdn-file-sharing
```

Run every command below from this folder. Use a new terminal for each numbered terminal.

## Run: D1 demo

Terminal 1 (controller, leave running):
```
sudo python3 run_controller.py controller.py
```

Terminal 2 (optional connectivity check):
```
sudo python3 topology.py -n 4
mininet> pingall
mininet> exit
sudo mn -c
```
Close this terminal before the next step. The topology and the demo cannot run at the same time.

Terminal 3:
```
sudo python3 run_demo.py
```
The demo prints five numbered stages and ends with `h4 valid login: SUCCESS (access restored)`. Then check the controller's decisions:
```
cat dynamic_events.csv
```

## Run: D2 experiments

With the controller still running in terminal 1, in a new terminal:
```
sudo python3 run_experiment.py --clients 4 --size-mb 20
cp results.csv results_n4.csv
sudo mn -c
cp results_n4.csv results.csv
python3 analyze.py
mv throughput.png throughput_n4.png
```
Repeat with `--clients 2` and `--clients 1`, changing the file names to match. `run_experiment.py` overwrites `results.csv` and `policy.json` each time. After the last run, restore `policy.json`:
```
echo '{"blocked_ips": [], "rate_limit_kbps": {}, "auto_block_seconds": 20}' > policy.json
```

Scenarios run by `run_experiment.py`:

- **baseline:** no policy, all clients transfer at the same time.
- **ratelimit:** h1 is capped at 5 Mbit/s by a meter.
- **block:** h4 is blocked by a priority-200 drop rule.

Each client uploads and then downloads a file of `--size-mb` MB. Metrics are throughput per client (Mbit/s) and Jain's fairness index.

## Results

Setup: one 100 Mbit/s link to the server shared by all clients, 20 MB per transfer.

4 clients:

| Scenario | Op | OK | Failed | Avg Mbit/s | Min | Max | Jain |
|---|---|---|---|---|---|---|---|
| baseline | download | 4 | 0 | 40.87 | 37.40 | 44.18 | 0.996 |
| baseline | upload | 4 | 0 | 30.41 | 23.63 | 37.76 | 0.953 |
| block | download | 3 | 1 | 40.64 | 36.02 | 46.02 | 0.990 |
| block | upload | 3 | 1 | 33.12 | 29.26 | 36.14 | 0.993 |
| ratelimit | download | 4 | 0 | 59.04 | 4.82 | 92.82 | 0.757 |
| ratelimit | upload | 4 | 0 | 31.63 | 5.00 | 57.84 | 0.740 |

Other client counts (baseline, average per client):

| Clients | Download Mbit/s | Upload Mbit/s |
|---|---|---|
| 1 | __ | __ |
| 2 | about 48 | about 48 |
| 4 | 40.87 | 30.41 |

D1 demo (h1, 5 MB, with the controller running):

| Test | Result |
|---|---|
| pingall | 0% dropped, 20/20 received |
| h1 upload / download | about 93 / 86 Mbit/s |
| h4 makes 3 wrong logins, then a valid login | 3 rejected, valid login times out (blocked) |
| h1 transfers while h4 is blocked | about 95 / 95 Mbit/s |
| h4 logs in after 25 s | succeeds; `dynamic_events.csv` has a block row and an unblock row |

Observations:

- Without a policy, clients share the server link fairly (Jain close to 1). Per-client throughput falls as clients are added.
- Blocking h4 does not affect the other clients' throughput.
- The meter holds h1 to about 5 Mbit/s and the remaining clients use the freed bandwidth. Jain drops because the split is uneven by design.
- The n=8 run failed and is not reported.

## Design decisions

- JSON header line plus raw bytes: the size field marks file boundaries on the TCP stream.
- One thread per client: simple and enough for a few clients.
- Events pass through a file in `/tmp` because Mininet hosts share the controller's filesystem, so no extra network path is needed.
- Drop rules use priority 200 so they override all learned flows. They are removed after a timeout.
- The controller runs through `run_controller.py` on os-ken, the maintained fork of Ryu.

## Limitations

- Single switch topology.
- No encryption (TLS); passwords are sent in the clear inside the emulated network.
- Password hashes are unsalted and the user list is hardcoded.
- The file-based event channel only works inside Mininet.
- Rate limits come from `policy.json`, not from automatic congestion detection.

## Troubleshooting

- Run `sudo mn -c` after every Mininet run, and before starting another.
- The `sch_htb: quantum of class ... is big` warnings are harmless.
- If apt reports a release file as "not valid yet", the VM clock is wrong. Set it with `timedatectl set-time`.
