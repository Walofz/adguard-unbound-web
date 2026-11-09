import os
import subprocess
import tomllib
from pathlib import Path

CONFIG_FILE = Path(os.environ.get("CONFIG_FILE", "/config/config.toml"))

# allowlist: subcommand ที่ webapp อนุญาตให้เรียกได้
ALLOWED = {
    "status", "stats", "stats_noreset",
    "list_forwards", "list_local_zones", "list_local_data",
    "reload", "flush_zone", "flush_bogus", "flush_negative",
}

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise RuntimeError(f"config file not found: {CONFIG_FILE}")
    return tomllib.loads(CONFIG_FILE.read_text())["unbound"]

def run(*args: str) -> tuple[int, str, str]:
    """Run an allow-listed unbound-control subcommand. Never uses shell=True."""
    if not args or args[0] not in ALLOWED:
        raise ValueError(f"command not allowed: {args[0]!r}")
    # กัน argument ที่ขึ้นต้นด้วย '-' ไม่ให้ถูกตีความเป็น option ของ unbound-control
    if any(a.startswith("-") for a in args[1:]):
        raise ValueError(f"invalid argument: {args[1:]!r}")
    cfg = load_config()
    cmd = [cfg["control_bin"], *cfg.get("control_args", []), *args]
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=cfg.get("timeout", 10), shell=False,
        )
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "command timed out"
    except FileNotFoundError:
        return 127, "", f"control binary not found: {cfg['control_bin']}"

def parse_stats(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        try:
            out[k] = float(v) if "." in v else int(v)
        except ValueError:
            out[k] = v
    return out


def _fmt_uptime(seconds: float) -> str:
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if not parts: parts.append(f"{s}s")
    return " ".join(parts)


def _num(raw: dict, key: str):
    """คืนค่าตัวเลข หรือ None ถ้า unbound ไม่ได้ส่ง key นี้มา."""
    v = raw.get(key)
    return v if isinstance(v, (int, float)) else None


def aggregate(raw: dict) -> dict:
    total_q = _num(raw, "total.num.queries") or 0
    hits    = _num(raw, "total.num.cachehits") or 0
    miss    = _num(raw, "total.num.cachemiss") or 0
    tcp     = _num(raw, "num.query.tcp")
    uptime  = _num(raw, "time.up") or 1
    rec_avg = _num(raw, "total.recursion.time.avg")
    rec_med = _num(raw, "total.recursion.time.median")

    qtypes, rcodes = {}, {}
    for k, v in raw.items():
        if not isinstance(v, (int, float)):
            continue
        if k.startswith("num.query.type."):
            qtypes[k[len("num.query.type."):]] = v
        elif k.startswith("num.answer.rcode."):
            rcodes[k[len("num.answer.rcode."):]] = v

    def val(key: str):
        v = _num(raw, key)
        return None if v is None else int(v)

    return {
        "qps": round(total_q / uptime, 2),
        "hit_ratio": round(hits / total_q * 100, 1) if total_q else 0.0,
        "queries": int(total_q),
        "hits": int(hits),
        "miss": int(miss),
        "uptime": int(uptime),
        "uptime_h": _fmt_uptime(uptime),
        "qtypes": qtypes,
        "rcodes": rcodes,
        # ตัวเลขพวกนี้ต้องเปิด extended-statistics: yes ที่ unbound ปลายทาง
        "extended": bool(qtypes or rcodes),
        "recursion_time_avg": round(rec_avg * 1000, 1) if rec_avg is not None else None,
        "recursion_time_median": round(rec_med * 1000, 1) if rec_med is not None else None,
        "secure": val("num.answer.secure"),
        "bogus": val("num.answer.bogus"),
        "tcp": None if tcp is None else int(tcp),
        "udp": None if tcp is None else int(total_q - tcp),
        "tls": val("num.query.tls"),
        "ipv6": val("num.query.ipv6"),
        "edns": val("num.query.edns.present"),
        "do": val("num.query.edns.DO"),
        "msg_cache": val("msg.cache.count"),
        "rrset_cache": val("rrset.cache.count"),
        "infra_cache": val("infra.cache.count"),
        "key_cache": val("key.cache.count"),
    }


def get_stats() -> tuple[dict | None, str | None]:
    rc, out, err = run("stats_noreset")
    if rc != 0:
        return None, err or f"(rc={rc})"
    return aggregate(parse_stats(out)), None