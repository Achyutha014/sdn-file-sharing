"""Simulates an unauthorised client: 3 wrong-password logins, then a correct login to show whether it is blocked.
python3 bruteforce.py --host 10.0.0.100"""
import argparse, time
from client import Client
ap = argparse.ArgumentParser(); ap.add_argument("--host", required=True); a = ap.parse_args()
for i in range(3):
    try:
        Client(a.host, "alice", "wrong-password", timeout=5)
    except PermissionError:
        print(f"attempt {i+1}: rejected (bad credentials)")
    except OSError as e:
        print(f"attempt {i+1}: network error {type(e).__name__}")
time.sleep(2)   # giving the controller a moment to react
try:
    c = Client(a.host, "alice", "alice123", timeout=5); c.close()
    print("RESULT: valid login SUCCEEDED (not blocked)")
except OSError as e:
    print(f"RESULT: valid login FAILED ({type(e).__name__}) -> client is BLOCKED by the SDN controller")
