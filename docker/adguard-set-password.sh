#!/bin/sh
# ตั้ง/รีเซ็ตรหัส admin ของ AdGuard Home (กรณีลืม หรือต้องการตั้งเป็น changeme)
# ใช้: ./adguard-set-password.sh <new-password>
set -e

PW="${1:?usage: $0 <new-password>}"
CONTAINER="${AGH_CONTAINER:-adguard-home}"

LINE=$(docker run --rm httpd:2.4-alpine htpasswd -nbBC 10 admin "$PW")
HASH=${LINE#*:}
HASH='$2a$'"${HASH#\$2y\$}"

# เปลี่ยนเฉพาะ password ของ user คนแรก (AdGuard default มี user เดียว)
docker exec -e HASH="$HASH" "$CONTAINER" sh -c \
  'sed -i "s|^    password: .*|    password: $HASH|" /opt/adguardhome/conf/AdGuardHome.yaml'

docker restart "$CONTAINER" >/dev/null
echo "AdGuard Home: password for 'admin' updated"
