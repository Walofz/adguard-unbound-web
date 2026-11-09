"""อ่าน/แปลง query log ของ unbound จากไฟล์ที่ mount เข้ามา

unbound ไม่มี API สำหรับดึงประวัติ query ผ่าน unbound-control
ต้องเปิด `log-replies: yes` (หรือ `log-queries: yes`) ที่ unbound ฝั่ง host
แล้วส่ง log มาไว้ที่ไฟล์นี้ (เช่น syslog forward / shared volume)
"""

import os
import re
from pathlib import Path

LOG_FILE = Path(os.environ.get("QUERY_LOG_FILE", "/logs/unbound.log"))
MAX_BYTES = int(os.environ.get("QUERY_LOG_MAX_BYTES", 1024 * 1024))

# [1699550000] unbound[123:0] reply: 192.168.1.10 example.com. A IN NOERROR 0.012345 0 55
# Nov  9 10:00:00 hostname unbound[123:0]: reply: 192.168.1.10 example.com. A IN NOERROR 0.012345 0 55
# [2026-11-09 10:00:00] unbound[123:0] info: 192.168.1.10 example.com. A IN
_LINE = re.compile(
    r"unbound\[\d+:\d+\]:?\s+(?P<kind>info|reply):\s+(?P<client>\S+)\s+(?P<qname>\S+)\s+"
    r"(?P<qtype>\S+)\s+(?P<qclass>\S+)"
    r"(?:\s+(?P<rcode>[A-Z]+)\s+(?P<elapsed>\d+(?:\.\d+)?)\s+"
    r"(?P<cached>\d+)\s+(?P<size>\d+))?"
)
_TS = re.compile(r"^\[(?P<ts>[^\]]+)\]")
_SYSLOG_TS = re.compile(r"^(?P<ts>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})")
_ADDR = re.compile(r"[0-9a-fA-F:.%]+")


def available() -> bool:
    return LOG_FILE.is_file()


def _tail(path: Path, max_bytes: int) -> list[str]:
    """อ่านท้ายไฟล์แบบไม่โหลดทั้งไฟล์ (log อาจใหญ่)."""
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        start = max(0, size - max_bytes)
        f.seek(start)
        data = f.read()
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if start > 0 and lines:
        lines = lines[1:]  # ตัดบรรทัดแรกที่อาจขาดกลาง
    return lines


def _parse(line: str):
    m = _LINE.search(line)
    if not m:
        return None
    d = m.groupdict()
    # กันบรรทัดที่ไม่ใช่ query เช่น "info: start of service ..." / "server stats for ..."
    if not d["qname"].endswith(".") or not _ADDR.fullmatch(d["client"]):
        return None
    ts_m = _TS.match(line) or _SYSLOG_TS.match(line)
    entry = {
        "kind": d["kind"],
        "ts": ts_m.group("ts") if ts_m else None,
        "client": d["client"],
        "qname": d["qname"],
        "qtype": d["qtype"],
        "qclass": d["qclass"],
        "rcode": d["rcode"],
        "elapsed": float(d["elapsed"]) if d["elapsed"] else None,
        "cached": bool(int(d["cached"])) if d["cached"] is not None else None,
        "size": int(d["size"]) if d["size"] is not None else None,
    }
    return entry


def read_queries(
    limit: int = 100,
    search: str = "",
    qtype: str = "",
    rcode: str = "",
) -> dict:
    info = {"available": available(), "path": str(LOG_FILE), "items": [], "total": 0}
    if not info["available"]:
        return info

    try:
        lines = _tail(LOG_FILE, MAX_BYTES)
    except OSError as exc:
        info["error"] = str(exc)
        return info

    entries = []
    for line in lines:
        e = _parse(line)
        if e:
            entries.append(e)

    if search:
        s = search.lower()
        entries = [e for e in entries if s in e["qname"].lower() or s in e["client"]]
    if qtype:
        entries = [e for e in entries if e["qtype"].upper() == qtype.upper()]
    if rcode:
        entries = [e for e in entries if (e["rcode"] or "").upper() == rcode.upper()]

    info["total"] = len(entries)
    info["items"] = entries[-limit:][::-1]
    return info
