# -*- coding: utf-8 -*-
"""
unfocused.py — ให้ขุดต่อได้แม้หน้าต่างเกมไม่ได้โฟกัส (alt-tab)

ปัญหา: เกมทุบบล็อกต่อเนื่องก็ต่อเมื่อ "เมาส์ถูกจับ" (MouseHandler.isMouseGrabbed) ซึ่งหน้าต่างที่ไม่โฟกัสจะไม่ถูกจับ
ต่อให้สคริปต์กดปุ่มโจมตีค้างไว้ (player_press_attack(True)) เกมก็ไม่ทุบ

วิธีแก้ (แนวเดียวกับ farm/tab_bridge.py แต่แยกเป็นอิสระ): ส่งสคริปต์ Pyjinn เข้าไปรันในเกม ทุกเฟรมที่
  ไม่มีหน้าจอเปิด + เมาส์ไม่ถูกจับ + ปุ่มโจมตีถูกกดค้างอยู่  →  สั่ง gameMode.continueDestroyBlock() ที่บล็อกที่เล็งอยู่
เหมือนที่เกมทำเองตอนโฟกัสปกติ ส่วนสถานะ (จำนวนครั้งที่ทุบ, เมาส์ถูกจับไหม, หน้าต่าง active ไหม) ส่งกลับมาทาง socket

ข้อจำกัด: ต้องเปิดแค่ตัวเดียว ห้ามรันพร้อม farm (ทั้งคู่ทุบบล็อกแทนเกม จะทุบซ้ำ)
         ต้องปิด "หยุดชั่วคราวเมื่อหน้าต่างไม่ได้โฟกัส" (options.txt: pauseOnLostFocus:false หรือ F3+P) ไม่งั้นเกมเปิดเมนู Pause
"""

import socket
import threading
import time

from system.lib.java import eval_pyjinn_script as eps

_STATS_INTERVAL_MS = 400


class UnfocusedAttack:
    def __init__(self, tick_ms: int = 50):
        self.tick_ms = int(tick_ms)
        self._lock = threading.Lock()
        self._stats = {"attacks": 0, "err": "", "grabbed": None, "active": None}
        self._connected = False
        self._started = False
        self._grab_changed_t = 0.0
        self._last_stats_t = 0.0

    # ----- สถานะ -----
    @property
    def connected(self) -> bool:
        """สคริปต์ในเกมต่อกลับมาแล้ว และส่งสถานะล่าสุดมาไม่เกิน 3 วินาทีที่แล้ว (ตายไปแล้ว = False)"""
        return self._connected and time.time() - self._last_stats_t < 3.0

    def stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    def grab_changed_at(self) -> float:
        """เวลาล่าสุดที่เมาส์เปลี่ยนสถานะจับ/ปล่อย (ตอนเมาส์ถูกจับคืน เกมตั้ง missTime=10000 ห้ามทุบจนกว่าจะปล่อยปุ่มตี)"""
        return self._grab_changed_t

    # ----- อ่านสถานะจากสคริปต์ในเกม -----
    def _handle_line(self, line: str) -> None:
        key, _, value = line.partition(":")
        with self._lock:
            if key == "ATTACKS":
                try:
                    self._stats["attacks"] = int(value)
                except ValueError:
                    return
            elif key == "ERR":
                self._stats["err"] = value
            elif key == "GRAB":
                grabbed = {"1": True, "0": False}.get(value)
                if grabbed is not None and grabbed != self._stats["grabbed"]:
                    self._grab_changed_t = time.time()
                self._stats["grabbed"] = grabbed
            elif key == "ACTIVE":
                self._stats["active"] = {"1": True, "0": False}.get(value)
                self._last_stats_t = time.time()   # ACTIVE เป็นบรรทัดท้ายของแต่ละชุด = หนึ่ง heartbeat

    def _reader(self, server) -> None:
        try:
            server.settimeout(15.0)
            conn, _ = server.accept()
            conn.settimeout(None)
            self._connected = True
            for line in conn.makefile(mode="r", encoding="utf-8"):
                self._handle_line(line.rstrip("\n"))
        except Exception:
            pass
        finally:
            self._connected = False

    # ----- เริ่ม -----
    def script_source(self, port: int) -> str:
        return r"""
mc = JavaClass("net.minecraft.client.Minecraft").getInstance()
System = JavaClass("java.lang.System")
Socket = JavaClass("java.net.Socket")
BufferedWriter = JavaClass("java.io.BufferedWriter")
OutputStreamWriter = JavaClass("java.io.OutputStreamWriter")
StandardCharsets = JavaClass("java.nio.charset.StandardCharsets")
InteractionHand = JavaClass("net.minecraft.world.InteractionHand")

sock = Socket("127.0.0.1", """ + str(int(port)) + r""")
writer = BufferedWriter(OutputStreamWriter(sock.getOutputStream(), StandardCharsets.UTF_8))
state = {"stats_t": 0, "atk_t": 0, "attacks": 0, "err": ""}

def frame(_):
    now = System.currentTimeMillis()
    try:
        if mc.gui.screen() is None and not mc.mouseHandler.isMouseGrabbed() and mc.options.keyAttack.isDown():
            if now - state["atk_t"] >= """ + str(self.tick_ms) + r""":
                state["atk_t"] = now
                hr = mc.hitResult
                if hr is not None and hr.getType().name() == "BLOCK":
                    bp = hr.getBlockPos()
                    if not mc.level.getBlockState(bp).isAir():
                        if mc.gameMode.continueDestroyBlock(bp, hr.getDirection()):
                            mc.player.swing(InteractionHand.MAIN_HAND)
                            state["attacks"] += 1
    except Exception as e:
        state["err"] = "attack: " + str(e)
    if now - state["stats_t"] < """ + str(_STATS_INTERVAL_MS) + r""":
        return
    state["stats_t"] = now
    try:
        g = "?"
        a = "?"
        try:
            g = "1" if mc.mouseHandler.isMouseGrabbed() else "0"
        except Exception as e:
            pass
        try:
            a = "1" if mc.isWindowActive() else "0"
        except Exception as e:
            pass
        writer.write("ATTACKS:" + str(state["attacks"]) + "\n")
        writer.write("ERR:" + state["err"].replace("\n", " ") + "\n")
        writer.write("GRAB:" + g + "\n")
        writer.write("ACTIVE:" + a + "\n")
        writer.flush()
    except Exception as e:
        pass

add_event_listener("render", frame)
"""

    def start(self) -> bool:
        """ส่งสคริปต์เข้าเกม คืน True ถ้าส่งสำเร็จ (ยังไม่รับประกันว่าต่อกลับมาแล้ว ดู .connected)"""
        if self._started:
            return True
        self._started = True
        try:
            server = socket.socket()
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            port = server.getsockname()[1]
            eps(self.script_source(port))
            threading.Thread(target=self._reader, args=(server,), daemon=True).start()
            return True
        except Exception:
            self._started = False
            return False
