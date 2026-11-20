"""Prepare the persistent account directory, drop privileges, and start Uvicorn."""
from __future__ import annotations

import os
import pwd
from pathlib import Path


def main() -> None:
    port = os.environ.get("PORT", "8080")
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise SystemExit("PORT must be an integer between 1 and 65535")

    db_path = Path(os.environ.get(
        "SUSSY_ACCOUNT_DB", "/var/lib/sussy-account/accounts.sqlite3"
    )).expanduser()
    data_dir = db_path.parent
    data_dir.mkdir(mode=0o750, parents=True, exist_ok=True)

    service_user = pwd.getpwnam("sussy")
    if os.geteuid() == 0:
        # Persistent disks can be mounted root-owned even when the image's
        # directory was chowned at build time. Only adjust the service data
        # directory and this application's SQLite files.
        os.chown(data_dir, service_user.pw_uid, service_user.pw_gid)
        os.chmod(data_dir, 0o750)
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(f"{db_path}{suffix}")
            if candidate.exists() and candidate.is_file():
                os.chown(candidate, service_user.pw_uid, service_user.pw_gid)
                os.chmod(candidate, 0o600)
        os.setgroups([])
        os.setgid(service_user.pw_gid)
        os.setuid(service_user.pw_uid)

    trusted_proxies = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")
    os.execvp("uvicorn", [
        "uvicorn", "app:app", "--host", "0.0.0.0", "--port", port,
        "--proxy-headers", "--forwarded-allow-ips", trusted_proxies,
    ])


if __name__ == "__main__":
    main()
