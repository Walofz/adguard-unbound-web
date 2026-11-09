# logs/

โฟลเดอร์นี้ถูก mount เข้า 2 container:

- `unbound` → `/logs` (เขียน `unbound.log`)
- `unbound-web` → `/logs` (อ่านอย่างเดียว)

ดังนั้น log ถูกเขียนโดย unbound ใน stack นี้เอง — **ไม่ต้องดึงจากเครื่องอื่น**

> ส่วน "วิธีดึง log จากเครื่องอื่น" ด้านล่างเก็บไว้เป็นกรณีใช้ unbound ภายนอก stack

## ต้องมีอะไรในโฟลเดอร์นี้

ไฟล์ `unbound.log` ที่ได้จาก unbound ฝั่ง host ซึ่งเปิดไว้แล้ว:

```yaml
server:
    log-replies: yes
    logfile: "/var/log/unbound.log"
```

> แนะนำ `log-replies: yes` อย่างเดียว จะได้ 1 บรรทัดต่อ 1 คำตอบ
> พร้อม rcode / ระยะเวลา / cache hit / ขนาด — ถ้าเปิด `log-queries: yes` ด้วย
> จะได้อีกบรรทัดต่อ query (อาจดูซ้ำ)

## วิธีดึง log จากเครื่อง unbound (192.168.1.250) มาที่นี่

เครื่องนี้กับเครื่อง unbound คนละเครื่อง (192.168.1.250 เปิด SSH ไว้แล้ว)

### Synology (Docker) — เคสของโปรเจกต์นี้

unbound รันใน container บน DSM → log อยู่ได้ 2 แบบ:

1. **stdout ของ container** (พบบ่อยใน image Docker) — เช็กด้วย
   `sudo docker logs --tail 5 <container>`
2. **ไฟล์ใน volume** — ดูจาก `sudo docker inspect <container> --format '{{json .Mounts}}'`
   แล้วเพิ่ม `log-replies: yes` ใน `unbound.conf` ที่อยู่ใน volume นั้น

#### ถ้า log ออกทาง stdout (แนะนำ)

ติดตั้ง `scripts/synology-unbound-log.sh` ไว้บน NAS แล้วสร้าง **Task Scheduler** (รันเป็น root)
ทุก 1 นาที — สคริปต์จะ append `docker logs` ลง `/volume1/docker/unbound-log/unbound.log`
(ตัดไฟล์ให้เหลือ 20 MB ท้าย)

จากนั้นบนเครื่องนี้ เพิ่ม cron ดึงไฟล์:

```bash
* * * * * rsync -az admin@192.168.1.250:/volume1/docker/unbound-log/unbound.log /home/walofz/unbound-web/logs/unbound.log
```

#### ถ้า log ถูกเขียนเป็นไฟล์ใน volume อยู่แล้ว

ไม่ต้องใช้ docker เลย — ชี้ rsync ไปที่ไฟล์นั้นตรง ๆ (ไม่ต้อง sudo ถ้า user อ่านได้):

```bash
* * * * * rsync -az admin@192.168.1.250:/volume1/docker/<stack>/logs/unbound.log /home/walofz/unbound-web/logs/unbound.log
```

### ทางเลือกอื่น

### A. ดึงสดด้วย `tail -F` ผ่าน SSH (แนะนำ)

```bash
# ครั้งเดียว: ถ้ายังไม่มี key
ssh-copy-id USER@192.168.1.250
ssh USER@192.168.1.250 'ls -l /var/log/unbound.log'
```

สร้าง `/etc/systemd/system/unbound-log-pull.service`:

```ini
[Unit]
Description=Pull unbound query log from 192.168.1.250
After=network-online.target
Wants=network-online.target

[Service]
User=walofz
ExecStart=/usr/bin/ssh -o ServerAliveInterval=30 USER@192.168.1.250 'tail -n 100 -F /var/log/unbound.log'
StandardOutput=append:/home/walofz/unbound-web/logs/unbound.log
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now unbound-log-pull
tail -f /home/walofz/unbound-web/logs/unbound.log   # เช็กว่าไหลมา
```

> SSH หลุด → systemd restart ให้เอง ; ไฟล์ log ที่นี่จะโตขึ้นเรื่อย ๆ
> (หน้าเว็บอ่านแค่ 1 MB ท้ายไฟล์) จะใส่ logrotate ก็ได้

### B. copy ทุกนาทีด้วย rsync

```bash
crontab -e
# เพิ่มบรรทัดนี้
* * * * * rsync -az USER@192.168.1.250:/var/log/unbound.log /home/walofz/unbound-web/logs/unbound.log
```

ถ้าฝั่ง remote มี log rotation ไฟล์จะถูกเขียนทับทั้งไฟล์ — หน้าเว็บอ่านท้ายไฟล์จึงยังใช้ได้

### C. syslog forward (ทางเลือก)

บนเครื่องนี้เปิดรับ syslog แล้วเขียนเฉพาะ program `unbound` ลงไฟล์
(`/etc/rsyslog.conf`) — ต้องให้ user `syslog` เขียนโฟลเดอร์ `logs/` ได้
หรือชี้ไป `/var/log/unbound/unbound.log` แล้วแก้ volume ใน compose เป็น
`/var/log/unbound:/logs:ro`

```conf
module(load="imtcp")
input(type="imtcp" port="514")
if $programname == 'unbound' then {
    action(type="omfile" file="/var/log/unbound/unbound.log")
    stop
}
```

แล้วฝั่ง unbound ตั้ง `*.* @@192.168.117.10:514` (หรือใช้ `rsyslog` ส่ง `omfwd`)

> 🔎 path ของ log ขึ้นกับอุปกรณ์: Linux ทั่วไป `/var/log/unbound.log`,
> pfSense/OPNsense `/var/log/resolver.log`, OpenWrt มักส่ง syslog อย่างเดียว
> (ไม่มี logfile) ต้องใช้วิธี C

> 🐳 **Synology DSM**: ถ้าใช้ Container Manager ให้ดูหัวข้อ "Synology (Docker)" ด้านบน
> และใช้ `scripts/synology-unbound-log.sh` ช่วยดึง `docker logs` ออกมาเป็นไฟล์

เปลี่ยน path ฝั่งเว็บได้ด้วย env `QUERY_LOG_FILE` ใน `docker/docker-compose.yml`

