# unbound-web — all-in-one (AdGuard Home + unbound + webapp)

Stack 3 container ที่ link กันใน docker network:

| service | หน้าที่ | port (host) |
|---|---|---|
| `adguard` | DNS front-end + บล็อกโฆษณา (cache off) → forward ไป unbound | 53, 3001 |
| `unbound` | recursive resolver + DNSSEC (config: `docker/unbound.conf`) | internal 53/8953 |
| `unbound-web` | dashboard + query log (FastAPI) | 8088 (ตั้งได้ด้วย `WEBAPP_PORT`) |

flow: client → AdGuard (block) → unbound (cache + DNSSEC) → upstream

- webapp ต่อ `unbound-control` ที่ **172.30.99.10:8953** (static IP ใน network `dnslink`)
- DNS ที่ publish ออก host คือของ AdGuard (`DNS_BIND` / `DNS_PORT`)
- query log ของ unbound อยู่ที่ `logs/unbound.log` (webapp อ่าน)
- ไม่ต้องตั้ง unbound บน host และไม่ต้องใช้ cert

---

## AdGuard Home (front-end + ad block)

- UI: `http://127.0.0.1:3001` (internal 3000, เปลี่ยน host port ด้วย `AGH_PORT`)
- cache ของ AdGuard **ปิด** (`cache_enabled: false`) — ให้ unbound เป็นคน cache/validate DNSSEC
- upstream = `172.30.99.10:53` (unbound)
- เปิด filter: AdGuard DNS filter + AdAway (~197k rules)
- ครั้งแรก: `cp .env.example .env` → ตั้ง `AGH_PASSWORD` → `docker compose up -d` →
  `docker compose --profile setup run --rm adguard-setup`
- เปลี่ยน password ภายหลังได้ที่ Settings → General (ค่าใน `.env` ใช้แค่ตอน setup ซ้ำ)

> ⚠️ เพราะ AdGuard เป็นคนรับ query จาก client แล้ว forward ต่อ — log ของ unbound จะเห็น client
> เป็น IP ของ container AdGuard (172.30.99.x) ทุกตัว; client IP จริง/สถานะ blocked ดูใน
> AdGuard UI → Query Log

### รหัสผ่านเริ่มต้น

| service | user | password | บังคับเปลี่ยน |
|---|---|---|---|
| `unbound-web` | `admin` | `changeme` | ✅ login ครั้งแรกบังคับเปลี่ยน (>= 12 ตัว) |
| `AdGuard Home` | `admin` | `changeme` | ❌ ไม่มีฟีเจอร์ — ไปเปลี่ยนที่ Settings → General |

```bash
# ตั้ง/รีเซ็ตรหัส webapp (--force = บังคับเปลี่ยนตอน login ครั้งถัดไป)
docker compose exec unbound-web python /app/manage.py set-password admin \
  --config /config/config.toml --password changeme --force

# ตั้ง/รีเซ็ตรหัส AdGuard Home
chmod +x adguard-set-password.sh
./adguard-set-password.sh changeme
```

> ถ้าเปลี่ยนรหัส AdGuard ใน UI แล้ว การรัน `adguard-setup` ซ้ำจะ login ไม่ได้
> จนกว่าจะอัปเดต `AGH_PASSWORD` ใน `docker/.env` ให้ตรงกัน

---

## ค่าเริ่มต้นของ unbound

แก้ที่ `docker/unbound.conf` — ไฟล์นี้ถูก copy เข้า image (`docker/Unbound.Dockerfile`)
จึงต้อง `docker compose up -d --build unbound` หลังแก้

มี `extended-statistics: yes` และ `log-replies: yes` เปิดไว้แล้ว

DNSSEC + root hints เปิดแล้ว:

- `auto-trust-anchor-file: /var/lib/unbound/root.key` — seed จาก `dns-root-data` ตอน build
  แล้ว unbound อัปเดต key เองด้วย RFC 5011 (ไม่ต้อง cron)
- `root-hints: /var/lib/unbound/root.hints` — entrypoint รีเฟรชจาก internic ทุก 7 วัน
  แล้ว `unbound-control reload` ให้อัตโนมัติ
- ทั้งสองไฟล์เก็บใน named volume `unbound-data` (อยู่ข้าม restart/recreate)

ทดสอบว่า validation ทำงาน:

```bash
# ต้องได้ AD flag
dig @127.0.0.1 cloudflare.com +dnssec | grep flags
# ต้องได้ SERVFAIL (โดเมนที่ DNSSEC เสีย)
dig @127.0.0.1 dnssec-failed.org | grep status
```

> การ `reload` รายสัปดาห์จะ reset counter ของ stats (queries/hits เริ่มนับใหม่)
> แต่ cache และ log ยังอยู่

- log หมุนอัตโนมัติเมื่อเกิน 20 MB (ตรวจทุกชั่วโมง → `unbound.log` + เก็บ `unbound.log.1`)
- `restart: unless-stopped` — บน Linux `docker.service` เปิดตอน boot อยู่แล้ว

### สิ่งที่ต้องเช็กบน Linux ก่อน deploy

1. **port 53** — publish จาก `adguard` ที่ `127.0.0.1:53` โดย default (ไม่ชน systemd-resolved ที่ `127.0.0.53`)
   ถ้าจะให้ LAN ใช้: `DNS_BIND=0.0.0.0` หรือระบุ IP จริงของเครื่อง เช่น `DNS_BIND=192.168.1.10`
   (ถ้าใช้ `0.0.0.0` แล้วชน port ให้ปิด stub listener ของ systemd-resolved)
2. **subnet ภายใน** — default `172.30.99.0/24` ถ้าชน network เดิม ให้ตั้งใน `docker/.env`:
   ```
   DNS_SUBNET=172.30.99.0/24
   UNBOUND_IP=172.30.99.10
   ```
   (`UNBOUND_IP` ถูกใช้ bootstrap `control-interface` ให้เองตอนสร้าง config ครั้งแรก)
3. **config/** — ต้องมีโฟลเดอร์และเจ้าของตรงกับ `WEBAPP_UID`/`WEBAPP_GID`
   ถ้าย้ายจากเครื่องเดิม ให้ copy `config/config.toml` + `config/unbound-client.conf` ไปเลย
   (มี secret_key และ user อยู่แล้ว ไม่ต้อง init ใหม่)
4. **SELinux** (Fedora/RHEL) — compose ใส่ `:z` ให้แล้ว
5. **internet ตอน build** — ต้องดาวน์โหลด apt packages + root hints

### เปิดให้ LAN ใช้งานทั้งหมด (Ubuntu)

**1) ตั้งค่า `docker/.env`**

```dotenv
DNS_BIND=0.0.0.0
AGH_BIND=0.0.0.0
WEBAPP_BIND=0.0.0.0
```

**2) ปิด stub listener ของ systemd-resolved**

`0.0.0.0:53` จะชนกับ `127.0.0.53:53` ของ systemd-resolved ถ้าไม่ปิด:

```bash
sudo mkdir -p /etc/systemd/resolved.conf.d
sudo tee /etc/systemd/resolved.conf.d/90-no-stub.conf >/dev/null <<'EOF'
[Resolve]
DNSStubListener=no
EOF
sudo systemctl restart systemd-resolved

# ให้ host ยัง resolve ได้ (ชี้ resolv.conf ไป upstream ของ resolved แทน stub)
sudo ln -sf /run/systemd/resolve/resolv.conf /etc/resolv.conf
```

ยืนยันว่า port ว่าง:

```bash
sudo ss -ltnup | grep ':53 ' || echo "port 53 ว่าง"
```

**3) recreate stack**

```bash
cd docker
docker compose down
docker compose up -d
docker compose ps
```

**4) เปิด firewall (ถ้าใช้ ufw)**

```bash
sudo ufw allow 53/udp
sudo ufw allow 53/tcp
sudo ufw allow 8088/tcp
sudo ufw allow 3001/tcp
```

**5) ทดสอบ**

```bash
dig @127.0.0.1 example.com
dig @<Ubuntu-LAN-IP> example.com        # จากเครื่องอื่นใน LAN
curl -I http://127.0.0.1:8088
curl -I http://127.0.0.1:3001
```

> **ทางเลือกที่ไม่ต้องปิด resolved:** ใช้ `DNS_BIND=<IP LAN ของเครื่อง>` เช่น `192.168.1.10`
> — bind เฉพาะ IP นั้น ไม่ชนกับ `127.0.0.53` และ LAN ใช้งานได้ปกติ
>
> เปิดสู่ LAN แล้วควรเปลี่ยนรหัสทั้งสอง UI และพิจารณา HTTPS
> (`session_https_only = true` ใน `config/config.toml` เมื่ออยู่หลัง reverse proxy TLS)

---

### 4) extended-statistics

`docker/unbound.conf` เปิด `extended-statistics: yes` ไว้แล้ว
ถ้าปิด ตัวเลข query type / response code / cache / DNSSEC จะเป็น `n/a` ใน dashboard

เช็ก:

```bash
docker compose exec unbound unbound-control -s 127.0.0.1 stats_noreset | grep num.query.type
```

> `statistics-inhibit-zero` มีค่า default เป็น `yes` — query type/rcode ที่เป็น 0 จะไม่ถูกส่งมา (ปกติ)

### 5) Query Log

`unbound-control` **ไม่มี** API ดึงประวัติ query — หน้า `/queries` อ่านจาก log file
ที่ unbound เขียนไว้ (`logfile: "/logs/unbound.log"` + `log-replies: yes` ใน `docker/unbound.conf`)

> เมื่อมี AdGuard อยู่ข้างหน้า unbound จะเห็น client เป็น IP ของ container AdGuard
> (172.30.99.x) — ถ้าต้องการ client IP จริง + สถานะ blocked ให้ดู Query Log ใน AdGuard UI
> (`http://127.0.0.1:3001`)

ไฟล์จริงอยู่ที่ `logs/unbound.log` ของโปรเจกต์ — ไม่ต้องส่ง log จากที่อื่น
เปลี่ยน path ได้ด้วย env `QUERY_LOG_FILE` (ทั้ง service)

---

## First run

```bash
cd docker
mkdir -p ../config ../adguard/conf ../adguard/work
sudo chown $(id -u):$(id -g) ../config
export WEBAPP_UID=$(id -u) WEBAPP_GID=$(id -g)   # ถ้าไม่ใช่ 1000

# AdGuard Home: ตั้ง password สำหรับ login ครั้งแรก
cp .env.example .env
# แก้ AGH_PASSWORD ใน .env ให้แข็งแรง

# ถ้ามี config/ จากเครื่องเดิมแล้ว (config.toml + unbound-client.conf) ข้าม init/add-user ได้
docker compose build

# สร้าง config.toml + unbound-client.conf (ชี้ไป service unbound ใน stack)
docker compose run --rm unbound-web \
  python /app/manage.py init --config /config/config.toml \
  --control-interface 172.30.99.10 --no-control-cert

# เพิ่ม user
docker compose run --rm unbound-web \
  python /app/manage.py add-user admin --config /config/config.toml

docker compose up -d

# ตั้ง AdGuard Home: cache off, upstream=unbound, เปิด filter บล็อกโฆษณา
docker compose --profile setup run --rm adguard-setup

docker compose logs -f
```

เปิด webapp http://127.0.0.1:8088 · AdGuard UI http://127.0.0.1:3001

> ถ้าต้องการให้เครื่องอื่นใน LAN เข้าหน้าเว็บได้ ใช้ `WEBAPP_BIND=0.0.0.0 docker compose up -d`
> (แนะนำให้วางหลัง reverse proxy ที่มี TLS และเปิด `session_https_only = true`)
>
> port 8953 ไม่ถูก publish — เข้าถึงได้เฉพาะ container ใน network `dnslink`

---

## ตรวจสอบการเชื่อมต่อจากใน container

```bash
docker compose exec unbound-web \
  unbound-control -c /config/unbound-client.conf status

# ควรเห็น:
# version: 1.17.x
# verbosity: 1
# threads: 2
# modules: 3 [ subnetcache validator iterator ]
# uptime: ...
# options: reuseport control
# unbound (pid 1) is running...
```

ถ้าเห็น `error: connect: Connection refused` → `docker compose ps unbound` ยังไม่ healthy
ถ้าเห็น `could not parse IP` → `config/unbound-client.conf` ต้องชี้ `172.30.99.10` ให้ตรงกับ static IP ใน compose

---

## ภาคผนวก: ต่อ unbound เครื่องอื่น (ไม่ใช้ service ใน stack)

ถ้าไม่ต้องการ unbound ใน stack ให้ลบ service `unbound` ออก (หรือ start เฉพาะ `unbound-web`)
แล้วชี้ `config/unbound-client.conf` ไปที่เครื่องนั้น เช่น

```yaml
remote-control:
    control-enable: yes
    control-interface: 192.168.1.250
    control-port: 8953
    control-use-cert: no      # เฉพาะ network ที่เชื่อถือได้
```

หรือเปิด TLS (`control-use-cert: yes` + mount `/etc/unbound:/certs:ro`) ตาม README เวอร์ชันก่อน

> ⚠️ `control-use-cert: no` บน TCP ที่เปิดสู่ภายนอก = ใครต่อถึงก็สั่งงาน unbound ได้