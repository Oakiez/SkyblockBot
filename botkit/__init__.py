# -*- coding: utf-8 -*-
"""
botkit — ชุดเครื่องมือกลางที่ farm.py และ mining.py ใช้ร่วมกัน

  settings.py   ค่าตั้งต้นทั้งหมด + โหลดค่าลับจาก farm/secrets_local.py
  discord_io.py ส่งข้อความ Discord (webhook สำหรับแจ้งเตือน, bot สำหรับตอบคำสั่ง) + ถ่ายภาพหน้าจอ
  remote.py     สั่งหยุด/พัก/ต่อ/ขอสถานะจาก Discord บนมือถือ (เฉพาะ user ID ที่อนุญาต)
  link.py       รวม heartbeat + remote + alert ไว้ที่เดียว
  reconnect.py  ต่อเซิร์ฟเวอร์ใหม่อัตโนมัติเมื่อหลุด (มีตัวกันหลายชั้น)
"""
