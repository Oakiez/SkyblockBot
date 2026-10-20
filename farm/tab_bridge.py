# -*- coding: utf-8 -*-
"""
tab_bridge.py — อ่าน tablist (Alive / Plots ของ pest) ผ่านสคริปต์ Pyjinn ที่รันในเกมโดยตรง

ทำไมไม่ใช้ JavaClass จาก Python: ทุกการเรียกเมธอด Java ต้องวิ่งไป-กลับระหว่าง process
ทีละครั้ง อ่าน tablist ทั้งหมดใช้เวลา 15–30 วินาที (วัดจาก log จริง) ส่วนสคริปต์ Pyjinn
รันใน JVM เดียวกับเกม อ่านจบในเสี้ยววินาที แล้วส่งผลกลับมาทาง socket
(รูปแบบเดียวกับ system/lib/lib_inv.py)
"""

import re
import socket
import threading
import time

from system.lib.java import eval_pyjinn_script as eps
from farm.config import TAB_BRIDGE_INTERVAL_MS

_latest = None        # (count, plots)
_latest_t = 0.0
_connected = False
_started = False
_input = {"grab": None, "active": None, "screen_frames": 0}   # สถานะเมาส์/หน้าต่างล่าสุดจากเกม (None = ไม่รู้)


def parse_tab_lines(lines):
    """รับข้อความบรรทัดของ tablist ที่มีคำว่า Alive/Plots คืน (count, plots)"""
    text = "\n".join(lines)
    count = 0
    plots = []
    m = re.search(r"Alive:\s*(\d+)", text)
    if m:
        count = int(m.group(1))
    m = re.search(r"Plots:\s*([^\n]*)", text)
    if m:
        plots = [x.strip() for x in m.group(1).split(",") if x.strip()]
    return count, plots


def latest(max_age: float = 3.0):
    """ค่าล่าสุดที่ได้จาก bridge ถ้าสดพอ ไม่งั้นคืน None"""
    if _latest is not None and time.time() - _latest_t <= max_age:
        return _latest
    return None


def is_connected() -> bool:
    return _connected


def screen_frames() -> int:
    """จำนวนเฟรมสะสมที่มี GUI เปิดอยู่ (นับในเกมทุกเฟรม ไม่ใช่ทุก 0.1 วินาที)"""
    return _input["screen_frames"]


def input_state():
    """(mouse_grabbed, window_active) ล่าสุด แต่ละค่าเป็น True/False/None(ไม่รู้)"""
    return _input["grab"], _input["active"]


def _reader(server):
    global _latest, _latest_t, _connected
    try:
        server.settimeout(15.0)
        conn, _ = server.accept()
        conn.settimeout(None)
        _connected = True
        buf = []
        for line in conn.makefile(mode="r", encoding="utf-8"):
            line = line.rstrip("\n")
            if line == "BEGIN":
                buf = []
            elif line == "END":
                _latest = parse_tab_lines(buf)
                _latest_t = time.time()
            elif line.startswith("GRAB:"):
                _input["grab"] = {"1": True, "0": False}.get(line[5:])
            elif line.startswith("SCREENFRAMES:"):
                try:
                    _input["screen_frames"] = int(line[13:])
                except ValueError:
                    pass
            elif line.startswith("ACTIVE:"):
                _input["active"] = {"1": True, "0": False}.get(line[7:])
            else:
                buf.append(line)
    except Exception:
        pass
    finally:
        _connected = False


def start() -> bool:
    """เริ่ม bridge (เรียกครั้งเดียวจาก main thread) คืน True ถ้าส่งสคริปต์เข้าเกมแล้ว"""
    global _started
    if _started:
        return True
    _started = True
    try:
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        eps(
            r"""
mc = JavaClass("net.minecraft.client.Minecraft").getInstance()
System = JavaClass("java.lang.System")
Socket = JavaClass("java.net.Socket")
BufferedWriter = JavaClass("java.io.BufferedWriter")
OutputStreamWriter = JavaClass("java.io.OutputStreamWriter")
StandardCharsets = JavaClass("java.nio.charset.StandardCharsets")

sock = Socket("127.0.0.1", """ + str(port) + r""")
writer = BufferedWriter(OutputStreamWriter(sock.getOutputStream(), StandardCharsets.UTF_8))
last = {"t": 0}
counts = {"screen": 0}

def frame(_):
    try:
        if mc.screen is not None:
            counts["screen"] += 1
    except Exception as e:
        pass
    now = System.currentTimeMillis()
    if now - last["t"] < """ + str(int(TAB_BRIDGE_INTERVAL_MS)) + r""":
        return
    last["t"] = now
    try:
        conn = mc.getConnection()
        if conn is None:
            return
        out = []
        for p in conn.getOnlinePlayers():
            d = p.getTabListDisplayName()
            if d is None:
                continue
            t = d.getString()
            if "Alive" in t or "Plots" in t:
                out.append(t)
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
        writer.write("SCREENFRAMES:" + str(counts["screen"]) + "\n")
        writer.write("GRAB:" + g + "\n")
        writer.write("ACTIVE:" + a + "\n")
        writer.write("BEGIN\n")
        for t in out:
            writer.write(t + "\n")
        writer.write("END\n")
        writer.flush()
    except Exception as e:
        pass

add_event_listener("render", frame)
"""
        )
        threading.Thread(target=_reader, args=(server,), daemon=True).start()
        return True
    except Exception:
        return False
