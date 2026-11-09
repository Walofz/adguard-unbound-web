# adguard/

ข้อมูลของ **AdGuard Home** (front-end DNS + ad blocking)

- `conf/` → `/opt/adguardhome/conf` (มี `AdGuardHome.yaml` = user, upstream, filters, cache)
- `work/` → `/opt/adguardhome/work` (query log DB, stats)

## ครั้งแรก

```bash
cd docker
cp .env.example .env          # แล้วตั้ง AGH_PASSWORD ให้แข็งแรง
docker compose up -d
docker compose --profile setup run --rm adguard-setup
```

สคริปต์จะตั้งให้:
- upstream = `unbound` (`172.30.99.10:53`)
- **cache = off** (ให้ unbound cache/validate DNSSEC)
- เปิด AdGuard DNS filter + AdAway

เข้า UI: `http://<host>:3001` (default bind `127.0.0.1`, internal port 3000)
เปลี่ยน password ได้ใน Settings → General

> หลังติดตั้งแล้ว ค่าใน `.env` ใช้แค่ตอนรัน setup ซ้ำ — password จริงเก็บเป็น hash ใน `conf/AdGuardHome.yaml`
