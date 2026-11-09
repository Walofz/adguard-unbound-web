#!/bin/bash
set -e

CONFIG_FILE="${CONFIG_FILE:-/config/config.toml}"

# 1) bootstrap config ถ้ายังไม่มี (ทำทุกครั้ง — ไม่ทำลายของเดิม)
if [ ! -f "$CONFIG_FILE" ]; then
    echo ">>> bootstrapping $CONFIG_FILE"
    if [ "${CONTROL_USE_CERT:-yes}" = "no" ]; then
        python /app/manage.py init --config "$CONFIG_FILE" \
            --control-interface "${CONTROL_INTERFACE:-127.0.0.1}" --no-control-cert
    else
        python /app/manage.py init --config "$CONFIG_FILE" \
            --control-interface "${CONTROL_INTERFACE:-127.0.0.1}"
    fi
fi

if [ ! -f /config/unbound-client.conf ] || [ ! -f "$CONFIG_FILE" ]; then
    echo ">>> ERROR: /config/unbound-client.conf หรือ $CONFIG_FILE หายไป" >&2
    exit 1
fi

# 2) ถ้ามี command ส่งมา (เช่น docker compose run ... python manage.py ...)
#    → exec command นั้นทันที ไม่ต้อง start server
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

# 3) ไม่มี command → start uvicorn (ปกติ)
echo ">>> probing unbound-control (TCP 8953) ..."
if python -c "import unbound; rc,o,e = unbound.run('status'); print((o or e).strip()); exit(0 if rc==0 else 1)"; then
    echo ">>> unbound-control reachable ✔"
else
    echo ">>> WARNING: unbound-control unreachable — starting anyway"
fi

echo ">>> starting uvicorn"
exec uvicorn main:app --host 0.0.0.0 --port 8080