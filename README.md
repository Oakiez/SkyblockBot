# SkyblockBot

บอทฟาร์ม Hypixel SkyBlock Garden สำหรับ [Minescript](https://minescript.net) เขียนด้วย Python
เดินฟาร์มตาม pattern ของพืชแต่ละชนิด กำจัด pest ด้วย AOTV + Vacuum รับบัฟ/สเปรย์ตามเวลา และสลับ loadout อัตโนมัติ

> ⚠️ **ความเสี่ยง:** การใช้สคริปต์ automation บน Hypixel ผิดกฎของเซิร์ฟเวอร์ และบัญชีอาจถูกแบนได้
> โปรเจกต์นี้ทำขึ้นเพื่อศึกษาและใช้ส่วนตัว ผู้ใช้รับผิดชอบความเสี่ยงเองทั้งหมด
> โปรเจกต์นี้ไม่มีและจะไม่เพิ่มฟีเจอร์ซ่อนตัวจากการตรวจจับ

## ความต้องการ

| รายการ | ที่ทดสอบด้วย |
|---|---|
| Minecraft (Fabric) | 26.2 |
| Minescript | 5.0 |
| Python | 3.13 (ตั้งใน `config.txt` ของ Minescript) |
| Mod เสริม | SkyHanni (ข้อความ pest cooldown), Skyblocker |

ไม่ต้องติดตั้ง mappings (`\install_mappings`) — โค้ดไม่ใช้ `minescript_plus` แล้ว
การคลิกในเมนูใช้ `system/lib/lib_inv.py` ที่มากับ Minescript

## ติดตั้ง

1. วางไฟล์ลงในโฟลเดอร์ `minescript/` ของโปรไฟล์ Minecraft
   ```
   minescript/
   ├── farm.py
   ├── villager.py
   ├── farm/
   └── tests/
   ```
2. สร้างไฟล์ `farm/secrets_local.py` (ไฟล์นี้ถูก `.gitignore` ไว้ ห้าม commit)
   ```python
   DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."   # ไม่บังคับ
   ```
3. ตั้งค่า hotbar และ loadout ให้ตรงกับ [การตั้งค่า](#การตั้งค่า) ด้านล่าง

## วิธีใช้

พิมพ์ในแชทเกม:

```
\farm              # ดูรายชื่อ profile
\farm wheat        # เริ่มบอทด้วย profile wheat
\villager          # รันตัวรับบัฟอย่างเดียว
```

| ปุ่ม | หน้าที่ |
|---|---|
| `]` | เริ่ม / หยุดฟาร์ม |
| `[` | พัก / เล่นต่อ (ปลดพักเองใน 30 วินาที) |

ปุ่มตั้งได้ที่ `PAUSE_KEY` / `START_STOP_KEY` ใน `farm/config.py`

### Profiles

`wheat`, `potato`, `carrot`, `wart`, `cane`, `cocoa`, `melon`, `pumpkin`, `cactus`, `mushroom`, `flower`
(แต่ละอันกำหนด `pattern`, `yaw`/`pitch`, จุดเริ่ม และ plot ที่จะ spray ใน `farm/profiles.py`)

## การทำงาน

1. **เริ่ม (`]`):** ลงพื้นถ้าลอยอยู่ → สลับ loadout (Pest ถ้ายังไม่มี pest, Farm ถ้ามี pest ค้างอยู่) → หันกล้อง → นับถอยหลัง 3 วินาที → คลิกซ้ายค้าง
2. **ฟาร์ม:** เดินตาม `pattern` ทีละเลนจนชนกำแพง (ตรวจจากการที่ตำแหน่งไม่ขยับ) แล้วเปลี่ยนเลน
3. **pest เกิด:** อ่านข้อความ `N Pest have spawned in Plot - X` จาก `logs/latest.log`
   ถ้าจำนวนถึง `AMOUNT_OF_PESTS` จะหยุดทันที `/setspawn` สลับเป็น Farm loadout แล้ว `/plottp` ไปกำจัด
   - บินขึ้นพ้นเพดาน → วาร์ปด้วย AOTV เข้าใกล้ pest → ดูดด้วย Vacuum
   - เสร็จแล้ว `/warp garden` กลับมาทำต่อ
4. **ท้ายรอบ:** ขายของ (`SELL_ITEMS`), รับบัฟ Phillip ทุก ~30 นาที (กดซ้อนไม่ได้), spray ทุก ~55 นาที (แยกนาฬิกากัน)
5. **Pest cooldown ใกล้หมด:** (SkyHanni แจ้งที่ 5 วินาที) สลับเป็น Pest loadout

### กลไกเสริม

| ไฟล์ | หน้าที่ |
|---|---|
| `farm/tab_bridge.py` | อ่าน tablist (Alive/Plots) ด้วยสคริปต์ Pyjinn ในเกม เร็วกว่าเรียก Java จาก Python ซึ่งวัดได้ 15–30 วินาทีต่อครั้ง |
| `farm/chatlog.py` | อ่านแชทจาก `logs/latest.log` เพราะ chat listener ของ Minescript ไม่ส่งข้อความระบบของเซิร์ฟเวอร์มาให้สคริปต์ |
| `farm/sensors.py` | poller กลาง เก็บตำแหน่ง/จำนวน pest เป็น cache |
| `farm/watchdog.py` | ถ้าตำแหน่งไม่ขยับ 30 วินาทีขณะฟาร์ม จะปล่อยปุ่ม `/warp garden` แล้วเริ่มรอบใหม่ |
| `farm/metrics.py` | จับเวลา step/plot/round สรุปตอนหยุดฟาร์ม |
| `farm/state.py` | state, `Mode` และคิว event (chat → main loop) |
| `farm/failsafe.py` | ตรวจเหตุผิดปกติที่เหมือนการตรวจ macro แล้วหยุดบอท |

## การตั้งค่า

แก้ที่ `farm/config.py` ที่เดียว:

| ค่า | ความหมาย |
|---|---|
| `FARM_LOADOUT_SLOT` / `PEST_LOADOUT_SLOT` | slot ในเมนู `/ld` (ตอนนี้ 15 / 14) |
| `VACUUM_SLOT` / `WARP_SLOT` | hotbar slot ของ Vacuum (2) และ AOTV (1) |
| `AMOUNT_OF_PESTS` | จำนวน pest ขั้นต่ำที่จะหยุดไปกำจัด (4) |
| `FLY_HEIGHT` / `FLY_BACKOFF_SECONDS` | ความสูงที่บินพ้นเพดาน / ถอยหลังก่อนบิน |
| `WARP_MIN_DISTANCE` | ไกลกว่านี้ให้วาร์ปเข้าไปก่อน (ระยะวาร์ปของ AOTV, 12) |
| `STUCK_CHECK_*` | ความไวการตรวจชนกำแพง |
| `BUFF_EVERY_SECONDS` / `SPRAY_EVERY_SECONDS` | รอบเวลารับบัฟ / spray |
| `PEST_USE_WARP` | `False` = กลับไปโหมดบินไล่แบบเดิม |
| `DEBUG_TIMING` | พิมพ์เวลาของแต่ละ step/plot |
| `SELL_ITEMS` | ไอเทมที่จะขายใน `/trades` |

พิกัดและ pattern ของแต่ละพืชอยู่ใน `farm/profiles.py`
พิกัด NPC รับบัฟอยู่ต้นไฟล์ `farm/buff.py`

## Failsafe (หยุดเมื่อเจอเหตุผิดปกติ)

`farm/failsafe.py` เฝ้าดูตอนบอทฟาร์มอยู่ ถ้าเจอเหตุที่ **เหมือนการตรวจ macro** จะ **หยุดบอททันที** ปล่อยปุ่ม แจ้งเตือนสีแดง แล้วรอให้ผู้เล่นตัดสินใจเอง (กด `]` เมื่อพร้อมเริ่มใหม่)

| เหตุที่ตรวจ | เกณฑ์ (ปรับที่ `farm/config.py`) |
|---|---|
| ถูกวาร์ป / ดึงตำแหน่ง | ตำแหน่งกระโดดเกิน `FAILSAFE_JUMP_BLOCKS` ในรอบเดียว |
| ถูกหันหัว | มุมกล้องเปลี่ยนเกิน `FAILSAFE_ROTATION_DEGREES` ที่สคริปต์ไม่ได้สั่ง |
| GUI โผล่ที่ไม่ได้สั่ง | GUI เปิดต่อเนื่อง หรือแว็บสั้น ๆ (นับเฟรมในเกมผ่าน bridge) |
| ถูกขังกล่อง bedrock | bedrock อย่างน้อย `FAILSAFE_BEDROCK_MIN_BLOCKS` จาก 9 จุดรอบตัว |

**ขอบเขตที่ตั้งใจ:** โมดูลนี้ตรวจแล้วหยุดเท่านั้น ไม่ตอบสนองการตรวจแทนผู้เล่น ไม่สุ่มพฤติกรรมให้ดูเหมือนคน และไม่ซ่อนว่าเป็นบอท

มีตัวเฝ้าสถานะ input ใน `farm/watchdog.py` ด้วย: ถ้าเมาส์ไม่ถูกจับหรือหน้าต่างเกมไม่ active ระหว่างฟาร์ม จะแจ้งเตือน `[Input] ...` และบอทกดคลิกซ้ายค้างซ้ำทุก `ATTACK_REASSERT_INTERVAL` เผื่อสถานะปุ่มหลุด

## ทดสอบ

ทดสอบ logic ออฟไลน์ได้โดยไม่ต้องเปิดเกม (stub Minescript ไว้):

```bash
python -m unittest discover -s tests -v
```

ครอบคลุม: การ import ทุกโมดูล, garden/profiles, state/event, การตั้งเวลาบัฟ/spray, parser ข้อความ pest, ตัวอ่าน log
ส่วนการเคลื่อนไหวและการคลิกจริงต้องทดสอบในเกมเท่านั้น

## ข้อจำกัดที่ยังมี

- ไม่มีโมดูลส่ง Discord (config มีค่า `DISCORD_WEBHOOK_URL` ไว้ แต่ยังไม่ได้เชื่อมกับโค้ด)
- หลังกำจัด pest กลางเลน บอทเริ่ม pattern ใหม่จากต้นเลนเดิม ไม่ได้เดินต่อจากจุดที่หยุด
- ตัวอ่านแชทและ bridge พึ่งพา path ของ `logs/latest.log` และพฤติกรรมของ Pyjinn ใน Minescript 5.0 อาจใช้ไม่ได้ในเวอร์ชันอื่น
- ค่าเวลาทั้งหมดปรับตามเครื่องและแล็กของแต่ละคน
