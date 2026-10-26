# sdn-file-sharing

# Concurrent File Sharing System with SDN Control (Project 14, D1)

All the D1 requirements are fulfilled here. 

A multi-user file-sharing application over TCP sockets, running in a Mininet network that is controlled by an
OpenFlow SDN controller (os-ken, the maintained fork of Ryu). The controller forwards, blocks and monitors the
file-transfer traffic, and it reacts to events reported by the file server: after repeated failed logins the server
notifies the controller, which blocks that host and later restores its access.

## Files
| File | Role |
|---|---|
| `common.py`, `server.py`, `client.py` | Multithreaded TCP file server (AUTH, LIST, UPLOAD, DOWNLOAD, SQLite metadata, SHA-256 checksums) and the client |
| `loadtest.py` | Transfer client used by the demo: uploads and downloads a random file and prints the speed |
| `bruteforce.py` | Simulates an unauthorised client (wrong passwords, then a valid login) |
| `controller.py` | OpenFlow 1.3 controller: learning switch, drop rules, flow-statistics bandwidth log (`bandwidth.csv`), reaction to application events (`dynamic_events.csv`) |
| `run_controller.py` | Launcher that starts the controller (the Ubuntu os-ken package has no `osken-manager` command) |
| `topology.py` | Mininet topology: server `srv` (10.0.0.100) and clients `h1`-`h4` (10.0.0.1-10.0.0.4) on one Open vSwitch switch, 100 Mbit/s links |
| `run_demo.py` | The full D1 demo (normal use, attack, block, recovery) |
| `policy.json` | Controller policy: blocked IPs, rate limits, `auto_block_seconds` (reloaded while the controller runs) |
| `screenshots/` | Test evidence |

## Environment
Ubuntu 26.04 (ARM64) VM in VirtualBox, Mininet, Open vSwitch and os-ken 4.1.1 (apt package). All commands need sudo.

## Setup
```
sudo apt update
sudo apt install -y mininet python3-os-ken git
git clone  https://github.com/Achyutha014/sdn-file-sharing.git
cd sdn-file-sharing
sudo mn --test pingall        # optional check, should end with: 0% dropped
```
If `apt update` reports a release file as "not valid yet", the VM clock is wrong. Set it, for example:
`sudo timedatectl set-ntp false && sudo timedatectl set-time "YYYY-MM-DD HH:MM:SS"`.

## Mininet setup check (before running the demo)

Run this once to confirm the network and controller work together.

**Terminal 1:** start the controller and leave it running
```
sudo python3 run_controller.py controller.py
```

**Terminal 2:** build the Mininet topology (1 switch, server `srv`, clients `h1` to `h4`)
```
sudo python3 topology.py -n 4
```
At the `mininet>` prompt, run:
```
pingall
```
Expected result: `0% dropped`.

After verifying the ping, type `exit` at the `mininet>` prompt, then clean up the leftover network setup:
```
sudo mn -c
```
Then proceed with the demo below.

## Run the D1 demo
Use two terminals, both in the project folder.
```
# Terminal 1: start the controller and leave it running
sudo python3 run_controller.py controller.py

# Terminal 2: run the demo (takes about a minute)
sudo python3 run_demo.py 2>&1 | grep -v sch_htb
```
The `grep` only hides harmless `sch_htb` warnings from Mininet's link-speed settings. The controller needs `sudo`
because the server runs as root inside Mininet and both share the event file `/tmp/sdnfs_events.jsonl`.

When finished, stop the controller with Ctrl+C and clean up with `sudo mn -c`.


## Expected output
1. **Connectivity:** ping from h1 to the server, 0% packet loss.
2. **Normal use:** h1 (alice) uploads and downloads a 5 MB file; a line with the speed is printed for each (about 90 Mbit/s).
3. **Attack:** h4 makes 3 wrong logins (`rejected (bad credentials)`), then a valid login times out, which means the controller has blocked h4.
4. **Others unaffected:** h1 transfers again while h4 is blocked. (will happen in D2)
5. **Recovery:** after 25 s, `h4 valid login: SUCCESS (access restored)`.

The controller's decisions are written to `dynamic_events.csv` (a `block` row and an `unblock` row) and its log shows
the matching `BLOCKING` and `restoring access` lines. Per-client bandwidth samples are in `bandwidth.csv`.

## How it works
- **Protocol:** each request is one JSON line (`AUTH`, `LIST`, `UPLOAD`, `DOWNLOAD`, `QUIT`). Uploads and downloads send a `size`, then exactly that many raw bytes in 64 KB chunks, and the receiver verifies the SHA-256.
- **Concurrency:** the server starts one thread per client connection.
- **Controller:** a table-miss rule sends unknown packets to the controller, which installs per-pair IP flows (priority 10) and MAC flows (priority 5) with a 30 s idle timeout. Drop rules for blocked hosts use priority 200.
- **Socket-SDN integration:** the server counts failed logins per client IP. After 3 failures within 60 s it appends an event to `/tmp/sdnfs_events.jsonl`. The controller reads the file every 0.5 s, installs drop rules for that IP, and removes them after `auto_block_seconds` (20 s in the demo).
- **Monitoring:** the controller polls flow statistics every 2 s and logs the Mbit/s of each client-server pair.

## Status against the problem statement
| Requirement | Status |
|---|---|
| Concurrent TCP file transfers | Implemented (thread per client) |
| Upload and download | Implemented, shown in the demo |
| File metadata | Implemented (SQLite table, `LIST`) |
| Authenticated access | Implemented, shown in the demo |
| SDN access policies | Blocking implemented and shown. Per-client rate limiting (OpenFlow meters) is implemented but not yet tested |
| Monitor bandwidth | Implemented (`bandwidth.csv`, controller log) |
| Test simultaneous transfers | Basic concurrent test done using loadtest.py, full evaluation part is planned for D2 |
| Evaluate transfer performance | Planned for D2 |

## Troubleshooting
- `osken-manager: command not found`: expected. Use `run_controller.py` as shown above.
- The controller will not stop with Ctrl+C: run `pkill -9 -f run_controller.py` from another terminal.
- Leftover Mininet state or odd network errors: run `sudo mn -c`, then start again.
- The `sch_htb: quantum of class ... is big` warnings when Mininet starts are harmless.

## Limitations
Demo users (alice, bob, carol) and their passwords are defined in `server.py`, and traffic is not encrypted.
