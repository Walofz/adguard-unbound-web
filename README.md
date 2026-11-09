# unbound-web

Stack สำหรับ self-host DNS resolver ส่วนตัว:

```text
client ──▶ AdGuard Home (บล็อกโฆษณา, cache off)
                │  forward
                ▼
           unbound (cache + DNSSEC + stats)
                │
                ▼
           upstream (1.1.1.1)

unbound-web (FastAPI) ──▶ unbound-control (8953, internal) ──▶ dashboard / query log
```

## Features

- **unbound** – recursive resolver, DNSSEC validation (RFC 5011), root hints รีเฟรชรายสัปดาห์
- **AdGuard Home** – DNS front-end + filter บล็อกโฆษณา (AdGuard DNS filter + AdAway, cache ปิด)
- **unbound-web** – dashboard สไตล์ AdGuard Home (light/dark), query log, สถิติจาก `unbound-control`
- บังคับเปลี่ยนรหัสผ่านครั้งแรกของ webapp, security headers, allow-list คำสั่ง `unbound-control`

## Quick start

```bash
cd docker
mkdir -p ../config ../adguard/conf ../adguard/work
sudo chown $(id -u):$(id -g) ../config

cp .env.example .env
# แก้ AGH_PASSWORD ใน .env

docker compose build
docker compose run --rm unbound-web \
  python /app/manage.py init --config /config/config.toml \
  --control-interface 172.30.99.10 --no-control-cert
docker compose run --rm unbound-web \
  python /app/manage.py add-user admin --config /config/config.toml

docker compose up -d
docker compose --profile setup run --rm adguard-setup
```

| service | URL / port |
|---|---|
| unbound-web | http://127.0.0.1:8088 (เปลี่ยน port ด้วย `WEBAPP_PORT`) |
| AdGuard Home | http://127.0.0.1:3001 |
| DNS | `127.0.0.1:53` (แก้ `DNS_BIND` ใน `.env` ให้ LAN ใช้) |

รหัสเริ่มต้น: `admin` / `changeme` ทั้งสองบริการ — webapp จะบังคับเปลี่ยนทันที,
AdGuard Home ให้เปลี่ยนที่ Settings → General

## Configuration

- `docker/unbound.conf` – config unbound (ถูก copy เข้า image; แก้แล้วต้อง `--build unbound`)
- `config/config.toml` – secret key + user (สร้างใหม่ด้วย `manage.py init`, ไม่อยู่ใน git)
- `docker/.env` – รหัส AdGuard สำหรับ setup + port bind (ไม่อยู่ใน git)
- `logs/unbound.log` – query log ที่หน้า `/queries` อ่าน (rotate 20 MB)
- `adguard/conf`, `adguard/work` – ข้อมูล AdGuard Home (ไม่อยู่ใน git)

รายละเอียดทั้งหมดดูที่ [`docker/README.md`](docker/README.md)

## Requirements

- Docker Engine / Docker Desktop + Compose v2
- internet ตอน build (apt packages + root hints)
- port 53 ว่างบน host (default bind `127.0.0.1`)

## Security notes

- `unbound-control` เปิดเฉพาะใน docker network (ไม่ publish 8953)
- webapp/AdGuard UI bind `127.0.0.1` โดย default
- เปลี่ยนรหัส `changeme` ก่อนเปิดใช้งานจริง และอย่า commit `config/config.toml` / `.env`
