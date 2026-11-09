#!/bin/sh
# รันบน Synology NAS (Task Scheduler แบบ root, ทุก 1 นาที)
# ดึง log ใหม่ของ container unbound แล้ว append ลง shared folder
# จากนั้นเครื่องที่รัน unbound-web ค่อย rsync ไฟล์นี้อีกที

CONTAINER="${CONTAINER:-unbound}"
OUTDIR="${OUTDIR:-/volume1/docker/unbound-log}"
LOG="$OUTDIR/unbound.log"
STATE="$OUTDIR/.since"

mkdir -p "$OUTDIR"

# ครั้งแรกย้อนหลัง 1 ชั่วโมง หลังจากนั้นใช้เวลาที่บันทึกไว้
if [ -f "$STATE" ]; then
    SINCE=$(cat "$STATE")
else
    SINCE=$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)
fi

docker logs --since "$SINCE" "$CONTAINER" >> "$LOG" 2>&1

# กันไฟล์โตไม่จำกัด: เก็บ 20 MB ท้ายไฟล์
if [ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 20971520 ]; then
    tail -c 20971520 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE"
