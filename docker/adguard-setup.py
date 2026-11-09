#!/usr/bin/env python3
"""ตั้งค่า AdGuard Home ให้เป็น front-end ของ unbound (idempotent)

- ปิด cache ของ AdGuard Home (ให้ unbound เป็นคน cache/validate)
- upstream ชี้ไป unbound ใน docker network (default 172.30.99.10:53)
- เปิด AdGuard DNS filter + AdAway

ใช้ครั้งแรกหลัง `docker compose up -d`:
    docker compose --profile setup run --rm adguard-setup
"""

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

AGH = os.environ.get("AGH_URL", "http://adguard:3000")
USER = os.environ.get("AGH_USER", "admin")
PASSWORD = os.environ.get("AGH_PASSWORD", "")
UPSTREAM = os.environ.get("UNBOUND_UPSTREAM", "172.30.99.10:53")

FILTERS = [
    ("AdGuard DNS filter",
     "https://adguardteam.github.io/HostlistsRegistry/assets/filter_1.txt"),
    ("AdAway Default Blocklist",
     "https://adguardteam.github.io/HostlistsRegistry/assets/filter_2.txt"),
]

AUTH = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()


def call(path: str, data=None, method: str | None = None, auth: bool = True):
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["Authorization"] = AUTH
    req = urllib.request.Request(
        AGH + path,
        data=json.dumps(data).encode() if data is not None else None,
        method=method or ("POST" if data is not None else "GET"),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode()
            if raw.strip().startswith(("{", "[")):
                return r.status, json.loads(raw)
            return r.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")


def wait_api():
    """รอให้ HTTP server ตอบ — หลังติดตั้งแล้ว endpoint install จะได้ 401/403 ก็ถือว่าถึงแล้ว"""
    for _ in range(60):
        try:
            with urllib.request.urlopen(AGH + "/", timeout=5):
                return True
        except urllib.error.HTTPError:
            return True
        except Exception:
            time.sleep(2)
    return False


def installed() -> bool:
    status, _ = call("/control/status")
    return status == 200


def main() -> int:
    if not PASSWORD:
        print("ERROR: ต้องตั้ง AGH_PASSWORD ใน docker/.env ก่อน", file=sys.stderr)
        return 2

    if not wait_api():
        print("ERROR: ติดต่อ AdGuard Home ไม่ได้", file=sys.stderr)
        return 1

    if not installed():
        print(">>> installing AdGuard Home ...")
        status, body = call("/control/install/configure", {
            "web": {"ip": "0.0.0.0", "port": 3000},
            "dns": {"ip": "0.0.0.0", "port": 53},
            "username": USER,
            "password": PASSWORD,
        }, auth=False)
        print("    install status:", status, body if status >= 400 else "")
        for _ in range(30):
            time.sleep(2)
            if installed():
                break

    if not installed():
        print("ERROR: login ไม่สำเร็จ (ตรวจ AGH_USER/AGH_PASSWORD)", file=sys.stderr)
        return 1

    # --- DNS config: cache off + upstream = unbound ---
    _, dns = call("/control/dns_info")
    dns.update({
        "upstream_dns": [UPSTREAM],
        "bootstrap_dns": ["1.1.1.1", "1.0.0.1"],
        "fallback_dns": [],
        "upstream_mode": "load_balance",
        "cache_enabled": False,
        "cache_size": 0,
        "ratelimit": 0,
        # unbound validate DNSSEC อยู่แล้ว ไม่ต้อง validate ซ้ำ
        "dnssec_enabled": False,
    })
    status, _ = call("/control/dns_config", dns)
    print(">>> dns_config:", status, f"(upstream={UPSTREAM}, cache=off)")

    # --- filters ---
    _, flt = call("/control/filtering/status")
    existing = {f.get("url"): f for f in flt.get("filters", [])}
    for name, url in FILTERS:
        if url in existing:
            status, _ = call("/control/filtering/set_url", {
                "url": url, "whitelist": False,
                "data": {"name": name, "url": url, "enabled": True},
            })
            print(f">>> enable filter: {name} ({status})")
        else:
            status, body = call("/control/filtering/add_url",
                                {"name": name, "url": url, "whitelist": False})
            print(f">>> add filter: {name} ({status})")
            if status >= 400:
                print("   ", body)

    call("/control/filtering/refresh", {"whitelist": False})
    _, flt = call("/control/filtering/status")
    total = sum(f.get("rules_count", 0) for f in flt.get("filters", []) if f.get("enabled"))
    print(f">>> filters active: {total:,} rules")

    # --- summary ---
    _, info = call("/control/dns_info")
    print(">>> done:",
          "upstream=", info.get("upstream_dns"),
          "cache=", info.get("cache_enabled"),
          "dnssec=", info.get("dnssec_enabled"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
