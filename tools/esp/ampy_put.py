#!/usr/bin/env python
"""
ampy_put — push local files to a MicroPython board via the ampy module API.

The `ampy` CLI subprocess sometimes fails on its first serial open with
"OSError: [Errno 2] ENOENT" from open(...,'wb') (CP2102 port state race on
Windows).  Driving files.Files.put through the module API in-process is
reliable, so this tool exists.

Usage:
    python tools/esp/ampy_put.py --port COM6 config.py config.py main.py main.py
    (pairs of LOCAL REMOTE; REMOTE may be omitted to use the local basename)

The port-state race makes the first attempt flaky (ENOENT = the exec ran
before the flash VFS was mounted after the soft reset), so each file is
retried with a fresh serial connection.
"""
from __future__ import annotations

import argparse
import sys
import time

from ampy import files, pyboard


def _put_with_retry(port: str, baud: int, remote: str, data: bytes,
                    attempts: int = 4) -> None:
    last = None
    for i in range(attempts):
        try:
            pb = pyboard.Pyboard(port, baudrate=baud)
            files.Files(pb).put(remote, data)
            return
        except Exception as exc:  # noqa: BLE001 - retry, then surface last
            last = exc
            try:
                pb.close()
            except Exception:
                pass
            time.sleep(1.5)
    raise last


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="serial port, e.g. COM6")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("pairs", nargs="+", metavar="LOCAL [REMOTE]",
                    help="local=remote pairs; remote defaults to basename")
    args = ap.parse_args()

    pairs: list[tuple[str, str]] = []
    it = iter(args.pairs)
    try:
        while True:
            local = next(it)
            remote = next(it, None)
            pairs.append((local, remote or local.rsplit("/", 1)[-1]))
    except StopIteration:
        pass

    for local, remote in pairs:
        with open(local, "rb") as f:
            data = f.read()
        _put_with_retry(args.port, args.baud, remote, data)
        print("pushed %-28s -> %s (%d bytes)" % (local, remote, len(data)))

    pb = pyboard.Pyboard(args.port, baudrate=args.baud)
    try:
        print("on-board listing:")
        for line in files.Files(pb).ls("/"):
            print("  ", line)
    finally:
        try:
            pb.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
