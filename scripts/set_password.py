"""Set a sign-in password for an employee (or reset the demo accounts).

    python scripts/set_password.py NT0082          # asks for the new password (not echoed)
    python scripts/set_password.py --demo          # demo personas get DEMO_PASSWORD from .env
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

from copilot.auth import DEMO_ACCOUNTS, set_password
import copilot.config  # noqa: F401  (loads .env)

DEFAULT_DEMO_PASSWORD = "nawa-demo-2026"   # fictional company, demo only — change DEMO_PASSWORD in .env


def demo_password() -> str:
    return os.getenv("DEMO_PASSWORD") or DEFAULT_DEMO_PASSWORD


def set_demo_passwords() -> int:
    pw = demo_password()
    for eid in DEMO_ACCOUNTS:
        set_password(eid, pw)
    return len(DEMO_ACCOUNTS)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("employee_id", nargs="?")
    ap.add_argument("--demo", action="store_true", help="reset all demo persona passwords")
    args = ap.parse_args()
    if args.demo:
        print(f"Set passwords for {set_demo_passwords()} demo accounts.")
        return 0
    if not args.employee_id:
        ap.error("give an employee ID or --demo")
    pw = getpass.getpass("New password: ")
    if pw != getpass.getpass("Repeat: "):
        print("Passwords do not match.")
        return 1
    set_password(args.employee_id.upper(), pw)
    print(f"Password set for {args.employee_id.upper()}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
