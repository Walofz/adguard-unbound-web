#!/bin/sh
set -e

mkdir -p /logs /var/lib/unbound

# log file ให้ user unbound เขียนได้ (unbound จะ drop privilege หลัง start)
touch /logs/unbound.log
chown unbound:unbound /logs/unbound.log 2>/dev/null || true
chmod 644 /logs/unbound.log 2>/dev/null || true

# trust anchor: ถ้า volume ยังว่าง ให้ seed จาก dns-root-data ที่ bake ไว้ใน image
if [ ! -s /var/lib/unbound/root.key ]; then
    cp /usr/share/dns/root.key /var/lib/unbound/root.key
fi
chown -R unbound:unbound /var/lib/unbound 2>/dev/null || true

fetch_hints() {
    curl -fsS --max-time 20 https://www.internic.net/domain/named.root \
        -o /var/lib/unbound/root.hints.tmp \
        && mv /var/lib/unbound/root.hints.tmp /var/lib/unbound/root.hints \
        && chown unbound:unbound /var/lib/unbound/root.hints
}

# refresh root hints ถ้าไม่มีหรือเก่ากว่า 7 วัน
if [ ! -s /var/lib/unbound/root.hints ] \
    || [ -n "$(find /var/lib/unbound/root.hints -mtime +7 2>/dev/null)" ]; then
    fetch_hints || echo ">>> WARNING: refresh root.hints failed (ใช้ไฟล์เดิมต่อ)"
fi

# งานเบื้องหลัง: ตรวจทุกชั่วโมง
#  - root.hints เก่ากว่า 7 วัน -> ดาวน์โหลดใหม่ + reload
#  - log ใหญ่เกิน 20 MB -> หมุนไฟล์ + log_reopen (กัน disk เต็ม)
(
    while sleep 3600; do
        if [ -n "$(find /var/lib/unbound/root.hints -mtime +7 2>/dev/null)" ]; then
            if fetch_hints; then
                unbound-control -c /etc/unbound/unbound.conf -s 127.0.0.1 reload || true
            fi
        fi

        if [ -f /logs/unbound.log ] && [ "$(wc -c < /logs/unbound.log)" -gt 20971520 ]; then
            mv /logs/unbound.log /logs/unbound.log.1
            touch /logs/unbound.log
            chown unbound:unbound /logs/unbound.log 2>/dev/null || true
            chmod 644 /logs/unbound.log
            unbound-control -c /etc/unbound/unbound.conf -s 127.0.0.1 log_reopen || true
        fi
    done
) &

exec /usr/sbin/unbound -d -c /etc/unbound/unbound.conf
