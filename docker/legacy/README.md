# legacy configs (ไม่ถูกใช้งาน)

ไฟล์ในโฟลเดอร์นี้เป็นของสถาปัตยกรรมแบบเก่า (all-in-one image ที่รัน unbound + webapp
ใน container เดียวด้วย supervisord) ซึ่ง **ไม่ถูกใช้แล้ว**

ปัจจุบัน image รันแค่ webapp (uvicorn) แล้วเรียก `unbound-control` ผ่าน TCP 8953
ไปยัง unbound ที่รันอยู่บน host

- `supervisord.conf` — ตัวรัน process แบบเก่า
- `unbound.conf` — ตัวอย่าง config ของ unbound ฝั่ง host (อ้างอิงเท่านั้น)
- `synology-unbound-log.sh` — สคริปต์เก่าสำหรับดึง log จาก unbound บน Synology
  (ไม่ต้องใช้แล้ว เพราะ unbound รันอยู่ใน stack นี้และเขียน `logs/unbound.log` เอง)

ตัวอย่าง config ที่ควรใช้ฝั่ง host อยู่ที่ `docker/README.md`
