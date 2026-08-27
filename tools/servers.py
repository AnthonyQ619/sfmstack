#!/usr/bin/env python3
"""What module servers are running, whose they are, and what they hold.

    tools/servers.py            list every sfmstack server, mine flagged
    tools/servers.py --orphans  only mine whose starting process is gone
    tools/servers.py --reap     stop those orphans
    tools/servers.py --reap-all stop ALL of mine, orphaned or not

Why this exists: a module server outlives the process that started it unless that
process exits cleanly, and until there was a label on the container there was no
way to ask "is this mine, and is anything still using it?". Four readers driving
this pipeline reported GPU exhaustion as "other tenants' processes" while every
container on the host was in fact their own -- a wrong diagnosis that reached the
written record because the question could not be asked.

`--reap-all` is the one to use when you are finished on a shared machine: normal
exit already reaps, but a killed process leaves servers behind, and on a host
other people share those hold devices until someone notices.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]
                       / "packages" / "sfmorch" / "src"))
from sfmorch.backends import OWNER_LABEL, PID_LABEL, _pid_alive  # noqa: E402

FMT = "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.RunningFor}}\t{{.Label \"%s\"}}\t{{.Label \"%s\"}}"


def rows() -> list[dict]:
    out = subprocess.run(
        ["docker", "ps", "--filter", "name=sfm-",
         "--format", FMT % (OWNER_LABEL, PID_LABEL)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        sys.exit(f"docker ps failed: {out.stderr.strip()}")

    me = os.getuid()
    result = []
    for line in out.stdout.splitlines():
        f = line.split("\t")
        if len(f) != 6:
            continue
        cid, name, image, age, uid, pid = f
        # Unlabelled containers predate the labels. They are reported so they are
        # not invisible, and never reaped: nothing here can prove they are ours.
        known = uid.isdigit()
        result.append({
            "id": cid, "name": name, "image": image, "age": age,
            "uid": int(uid) if known else None,
            "pid": int(pid) if pid.isdigit() else None,
            "mine": known and int(uid) == me,
            "orphan": (known and int(uid) == me and pid.isdigit()
                       and not _pid_alive(int(pid))),
            "unlabelled": not known,
        })
    return result


def gpu_holders() -> dict[int, int]:
    """host pid -> MiB, for whatever nvidia-smi will admit to."""
    out = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid,used_memory",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        return {}
    held = {}
    for line in out.stdout.splitlines():
        pid, mib = (p.strip() for p in line.split(","))
        if pid.isdigit() and mib.isdigit():
            held[int(pid)] = int(mib)
    return held


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--orphans", action="store_true", help="only servers whose process is gone")
    ap.add_argument("--reap", action="store_true", help="stop those orphans")
    ap.add_argument("--reap-all", action="store_true", help="stop every server of mine")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    all_rows = rows()
    shown = [r for r in all_rows if r["orphan"]] if (args.orphans or args.reap) else all_rows
    if args.reap_all:
        shown = [r for r in all_rows if r["mine"]]

    if args.json:
        print(json.dumps(shown, indent=1))
    else:
        held = gpu_holders()
        mine = sum(1 for r in all_rows if r["mine"])
        orph = sum(1 for r in all_rows if r["orphan"])
        print(f"{len(all_rows)} sfmstack server(s) running; {mine} mine, {orph} orphaned")
        for r in shown:
            tag = "ORPHAN" if r["orphan"] else ("mine" if r["mine"] else
                                                "unlabelled" if r["unlabelled"] else "other user")
            gpu = f"  {held[r['pid']]}MiB" if r["pid"] in held else ""
            print(f"  {r['name']:42} {r['image']:34} up {r['age']:16} {tag}{gpu}")

    if args.reap or args.reap_all:
        killed = 0
        for r in shown:
            if subprocess.run(["docker", "rm", "-f", r["id"]],
                              capture_output=True).returncode == 0:
                killed += 1
        print(f"stopped {killed} server(s)")


if __name__ == "__main__":
    main()
