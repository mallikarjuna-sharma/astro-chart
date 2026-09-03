#!/usr/bin/env python3
"""Download NASA JPL DE421 ephemeris to the repo root for production deploy.

de421.bsp is gitignored (~17MB). Render/CI must fetch it during build so
Prashna and other Skyfield-backed features work at runtime.
"""
from __future__ import annotations

from pathlib import Path

from skyfield.api import Loader

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = REPO_ROOT / "de421.bsp"


def main() -> None:
    if TARGET.is_file():
        print(f"de421.bsp already present at {TARGET} ({TARGET.stat().st_size:,} bytes)")
        return

    print(f"Downloading de421.bsp to {TARGET} ...")
    loader = Loader(str(REPO_ROOT))
    loader("de421.bsp")

    if not TARGET.is_file():
        raise SystemExit(f"Download failed: {TARGET} not found after load()")

    print(f"OK: de421.bsp ready ({TARGET.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
