import os
import tomllib
from pathlib import Path

import tomli_w
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.exception_handlers import http_exception_handler
from starlette.middleware.sessions import SessionMiddleware
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

import unbound
import querylog

CONFIG_FILE = Path(os.environ.get("CONFIG_FILE", "/config/config.toml"))
if not CONFIG_FILE.exists():
    raise RuntimeError(f"config file not found: {CONFIG_FILE}")

cfg = tomllib.loads(CONFIG_FILE.read_text())
_app = cfg["app"]

app = FastAPI(title="unbound-web")
app.add_middleware(
    SessionMiddleware,
    secret_key=_app["secret_key"],
    same_site="lax",
    https_only=_app.get("session_https_only", False),
    max_age=_app.get("session_max_age", 43200),
)
templates = Jinja2Templates(directory="templates")


def _num_filter(value):
    """จัดรูปแบบตัวเลขใน template; ค่า None (unbound ไม่ส่งมา) แสดงเป็น n/a."""
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.1f}"
    return f"{value:,}"


templates.env.filters["num"] = _num_filter
ph = PasswordHasher()

def verify(username: str, password: str) -> bool:
    h = cfg.get("users", {}).get(username)
    if not h:
        return False
    try:
        return ph.verify(h, password)
    except (VerifyMismatchError, VerificationError):
        return False


def must_change(username: str) -> bool:
    return bool(cfg.get("force_change", {}).get(username, False))


def session_user(request: Request) -> str:
    """ผู้ใช้ที่ login แล้ว (ยังไม่บังคับเปลี่ยนรหัส)."""
    u = request.session.get("user")
    if not u:
        raise HTTPException(401)
    return u


def current_user(request: Request) -> str:
    """ผู้ใช้ที่พร้อมใช้งาน — ถ้ายังไม่เปลี่ยนรหัสครั้งแรกจะโดน 428."""
    u = session_user(request)
    if must_change(u):
        raise HTTPException(428)
    return u


def save_password(username: str, password: str) -> None:
    """อัปเดต hash + เคลียร์ flag บังคับเปลี่ยนรหัส แล้วเขียน config.toml."""
    cfg.setdefault("users", {})[username] = ph.hash(password)
    cfg.setdefault("force_change", {})[username] = False
    tmp = CONFIG_FILE.with_name(CONFIG_FILE.name + ".tmp")
    tmp.write_text(tomli_w.dumps(cfg))
    tmp.chmod(0o600)
    tmp.replace(CONFIG_FILE)


def _control_result(rc: int, out: str, err: str) -> JSONResponse:
    body = {"ok": rc == 0, "rc": rc, "out": out.strip(), "err": err.strip()}
    return JSONResponse(body, status_code=200 if rc == 0 else 502)


@app.exception_handler(HTTPException)
async def redirect_on_401(request: Request, exc: HTTPException):
    # endpoint ใต้ /api ต้องได้ JSON (ไม่ redirect) เพื่อให้ frontend รู้สถานะ
    if exc.status_code == 428:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "password change required"}, status_code=428)
        return RedirectResponse("/change-password", status_code=303)
    if exc.status_code == 401:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return RedirectResponse("/login", status_code=303)
    return await http_exception_handler(request, exc)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'",
    )
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


@app.get("/health")
def health(deep: bool = False):
    # shallow: ตรวจแค่ว่า config โหลดได้ (ไม่ block ตอน unbound ล่ม)
    u = unbound.load_config()
    if not deep:
        return {"ok": True, "control_bin": u["control_bin"]}
    s, err = unbound.get_stats()
    if s is None:
        raise HTTPException(503, err or "unbound-control unavailable")
    return {"ok": True, "control_bin": u["control_bin"], "extended": s["extended"]}

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")

@app.post("/login")
def login_submit(request: Request,
                 username: str = Form(...),
                 password: str = Form(...)):
    if verify(username, password):
        request.session.clear()
        request.session["user"] = username
        target = "/change-password" if must_change(username) else "/"
        return RedirectResponse(target, status_code=303)
    return templates.TemplateResponse(
        request, "login.html",
        {"error": "Invalid credentials"},
        status_code=401,
    )


@app.get("/change-password", response_class=HTMLResponse)
def change_password_page(request: Request, user: str = Depends(session_user)):
    return templates.TemplateResponse(request, "change_password.html", {
        "user": user,
        "forced": must_change(user),
    })


@app.post("/change-password")
def change_password_submit(request: Request,
                           current: str = Form(...),
                           new: str = Form(...),
                           confirm: str = Form(...),
                           user: str = Depends(session_user)):
    error = None
    if not verify(user, current):
        error = "รหัสผ่านปัจจุบันไม่ถูกต้อง"
    elif len(new) < 12:
        error = "รหัสใหม่ต้องอย่างน้อย 12 ตัวอักษร"
    elif new != confirm:
        error = "รหัสใหม่ทั้งสองช่องไม่ตรงกัน"
    elif new == current:
        error = "รหัสใหม่ต้องไม่ซ้ำกับรหัสเดิม"
    if error:
        return templates.TemplateResponse(request, "change_password.html", {
            "user": user,
            "forced": must_change(user),
            "error": error,
        }, status_code=400)
    save_password(user, new)
    return RedirectResponse("/", status_code=303)

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, user: str = Depends(current_user)):
    rc_s, status, err_s = unbound.run("status")
    s, err = unbound.get_stats()
    return templates.TemplateResponse(request, "dashboard.html", {
        "user": user,
        "status": (status or err_s or f"(rc={rc_s})").strip(),
        "s": s,
        "err": err,
    })


@app.get("/api/stats")
def api_stats(user: str = Depends(current_user)):
    s, err = unbound.get_stats()
    if s is None:
        raise HTTPException(503, err or "unbound-control unavailable")
    return s


@app.get("/queries", response_class=HTMLResponse)
def queries_page(request: Request, user: str = Depends(current_user)):
    return templates.TemplateResponse(request, "queries.html", {
        "user": user,
        "log_path": str(querylog.LOG_FILE),
        "available": querylog.available(),
    })


@app.get("/api/queries")
def api_queries(limit: int = 50, q: str = "", qtype: str = "", rcode: str = "",
                user: str = Depends(current_user)):
    limit = max(1, min(limit, 200))
    return querylog.read_queries(limit=limit, search=q, qtype=qtype, rcode=rcode)


@app.get("/api/response-codes")
def api_response_codes(user: str = Depends(current_user)):
    result = querylog.read_queries(limit=1000)
    counts = {}
    for entry in result["items"]:
        code = entry["rcode"]
        counts[code] = counts.get(code, 0) + 1
    return {
        "available": result["available"],
        "counts": counts,
        "total": len(result["items"]),
        "limit": 1000,
    }

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

@app.post("/reload")
def do_reload(user: str = Depends(current_user)):
    rc, out, err = unbound.run("reload")
    return _control_result(rc, out, err)


@app.post("/flush")
def do_flush(zone: str = Form(""), user: str = Depends(current_user)):
    try:
        if zone:
            rc, out, err = unbound.run("flush_zone", zone)
        else:
            rc, out, err = unbound.run("flush_bogus")
    except ValueError as exc:
        return JSONResponse({"ok": False, "rc": 2, "out": "", "err": str(exc)}, status_code=400)
    return _control_result(rc, out, err)