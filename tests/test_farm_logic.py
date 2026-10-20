# -*- coding: utf-8 -*-
"""
ทดสอบ logic ล้วน ๆ ของ farm/ ออฟไลน์ (ไม่ต้องเปิดเกม) โดย stub minescript ทิ้ง

รัน:  python -m unittest discover -s tests -v   (จากโฟลเดอร์ minescript)
ครอบคลุม: import ทุกโมดูลไม่พัง (circular import), garden, profiles, state/events,
          wait_until, metrics, ตัวตัดสินใจ spray
"""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

for _name in (
    "system",
    "system.lib",
    "system.lib.minescript",
    "system.lib.java",
    "system.lib.lib_inv",
):
    sys.modules.setdefault(_name, MagicMock())

import farm.state as state  # noqa: E402
from farm import metrics  # noqa: E402
from farm.garden import PLOT_CENTERS, GARDEN_LAYOUT  # noqa: E402
from farm.profiles import FARM_PROFILES  # noqa: E402
from farm.utils import wait_until  # noqa: E402


class ImportTests(unittest.TestCase):
    def test_all_modules_import(self):
        import importlib

        for name in (
            "farm.config", "farm.utils", "farm.movement", "farm.inventory",
            "farm.pest", "farm.recovery", "farm.buff", "farm.sensors",
            "farm.watchdog", "farm.farm_loop",
        ):
            with self.subTest(module=name):
                importlib.import_module(name)


class GardenTests(unittest.TestCase):
    def test_every_plot_has_center_inside_garden(self):
        plots = {p for row in GARDEN_LAYOUT for p in row}
        self.assertEqual(plots, set(PLOT_CENTERS))
        for plot, (x, z) in PLOT_CENTERS.items():
            self.assertTrue(-239 <= x <= 239 and -239 <= z <= 239, plot)


class ProfileTests(unittest.TestCase):
    def test_profiles_have_required_keys(self):
        for name, p in FARM_PROFILES.items():
            with self.subTest(profile=name):
                for key in ("name", "yaw", "pitch", "pattern", "start_pos"):
                    self.assertIn(key, p)
                self.assertTrue("tool_id" in p or "tool_name" in p)
                self.assertTrue(p["pattern"])
                for step in p["pattern"]:
                    self.assertIn(step["direction"], ("left", "right", "forward", "backward"))

    def test_wheat_is_right_left_x17(self):
        p = FARM_PROFILES["wheat"]
        dirs = [s["direction"] for s in p["pattern"]]
        self.assertEqual(len(dirs), 34)
        self.assertEqual(dirs[:4], ["right", "left", "right", "left"])
        self.assertEqual(p["spray_plots"], [4])


class StateTests(unittest.TestCase):
    def setUp(self):
        state.clear_events()

    def test_events_fifo_and_clear(self):
        state.post_event("A")
        state.post_event("B")
        self.assertEqual(state.poll_event(), "A")
        state.clear_events()
        self.assertIsNone(state.poll_event())

    def test_in_mode_restores(self):
        state.mode = state.Mode.FARMING
        with state.in_mode(state.Mode.PEST):
            self.assertEqual(state.mode, state.Mode.PEST)
        self.assertEqual(state.mode, state.Mode.FARMING)

    def test_in_mode_restores_on_error(self):
        state.mode = state.Mode.FARMING
        with self.assertRaises(RuntimeError):
            with state.in_mode(state.Mode.SPRAY):
                raise RuntimeError("boom")
        self.assertEqual(state.mode, state.Mode.FARMING)


class UtilTests(unittest.TestCase):
    def test_wait_until_true_and_timeout(self):
        t0 = time.time()
        self.assertTrue(wait_until(lambda: True, 1.0))
        self.assertLess(time.time() - t0, 0.2)
        self.assertFalse(wait_until(lambda: False, 0.1))


class MetricsTests(unittest.TestCase):
    def test_summary(self):
        metrics.reset()
        metrics.record("step", 1.0)
        metrics.record("step", 3.0)
        lines = metrics.summary_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn("n=2", lines[0])
        self.assertIn("avg=2.00s", lines[0])


class PestSpawnMessageTests(unittest.TestCase):
    def setUp(self):
        import farm.recovery as rec

        self.rec = rec

    def test_parse_plural_with_symbol_and_colors(self):
        msg = "§6§lYUCK! §r§c6 §r§cൠ Pest §r§fhave spawned in §r§aPlot - 4§r§f! §e§lCLICK HERE§r to teleport to the plot!"
        self.assertEqual(self.rec.parse_pest_spawn(msg), (6, 4))

    def test_parse_single(self):
        self.assertEqual(self.rec.parse_pest_spawn("YUCK! 1 ൠ Pest has spawned in Plot - 12!"), (1, 12))

    def test_ignores_other_chat(self):
        self.assertIsNone(self.rec.parse_pest_spawn("Pest spawn cooldown expires in 1s"))
        self.assertIsNone(self.rec.parse_pest_spawn("hello world"))

    def test_trigger_posts_event_even_while_switching(self):
        state.clear_events()
        state.is_running = True
        state.cycling_pests = False
        state.changing_outfit = True      # เดิมข้อความถูกทิ้งตรงนี้
        state.last_pest_spawn_time = 0
        try:
            ok = self.rec.check_for_pest_spawn_message("YUCK! 6 ൠ Pest have spawned in Plot - 4!")
            self.assertTrue(ok)
            self.assertEqual(state.poll_event(), "PEST_SPAWNED")
            self.assertEqual(state.last_spawn_info, (6, 4))
        finally:
            state.is_running = False
            state.changing_outfit = False


class BridgeAndChatlogTests(unittest.TestCase):
    def test_parse_tab_lines(self):
        from farm.tab_bridge import parse_tab_lines

        lines = ["§6Alive: §c6", "§6Plots: §b4, 12"]
        self.assertEqual(parse_tab_lines([l.replace("§6", "").replace("§c", "").replace("§b", "") for l in lines]), (6, ["4", "12"]))
        self.assertEqual(parse_tab_lines([]), (0, []))

    def test_extract_chat(self):
        from farm.chatlog import extract_chat

        line = "[04:16:03] [Render thread/INFO]: [System] [CHAT] §6§lYUCK! §26 §2 Pest §7have spawned in §aPlot §7- §b12§7!"
        self.assertTrue(extract_chat(line).startswith("§6§lYUCK!"))
        self.assertIsNone(extract_chat("[04:16:03] [Render thread/INFO]: saved currency.json"))

    def test_tail_delivers_new_lines_only(self):
        import tempfile
        import threading
        from farm import chatlog

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "latest.log")
            with open(path, "wb") as f:
                f.write(b"[00:00:00] [Render thread/INFO]: [System] [CHAT] OLD line\n")
            got = []
            stop = {"v": False}
            t = threading.Thread(
                target=chatlog.tail, args=(path, [got.append], 0.02, lambda: stop["v"]), daemon=True
            )
            t.start()
            time.sleep(0.15)
            with open(path, "ab") as f:
                f.write("[00:00:01] [Render thread/INFO]: [System] [CHAT] YUCK! 6 Pest have spawned in Plot - 4!\n"
                        "[00:00:01] [x]: saved skill.json\n".encode("utf-8"))
            time.sleep(0.3)
            stop["v"] = True
            t.join(timeout=1)
            self.assertEqual(got, ["YUCK! 6 Pest have spawned in Plot - 4!"])   # ไม่เอาของเก่า ไม่เอาบรรทัดที่ไม่ใช่แชท


class PestCycleLoadoutTests(unittest.TestCase):
    def test_switches_to_farm_before_first_plot(self):
        import farm.inventory as inv
        import farm.pest as pest

        calls = []
        orig = (inv.switch_to_farming_outfit, pest.vacuum_plot, pest._plots_to_clear)
        inv.switch_to_farming_outfit = lambda: calls.append("farm_loadout")
        pest.vacuum_plot = lambda plot, timeout=0: calls.append("plot " + str(plot))
        pest._plots_to_clear = lambda: ["4", "12"]
        state.is_running = True
        try:
            pest.pest_cycle()
        finally:
            state.is_running = False
            inv.switch_to_farming_outfit, pest.vacuum_plot, pest._plots_to_clear = orig
        self.assertEqual(calls, ["farm_loadout", "plot 4", "plot 12"])

    def test_no_switch_when_no_pests(self):
        import farm.inventory as inv
        import farm.pest as pest

        calls = []
        orig = (inv.switch_to_farming_outfit, pest._plots_to_clear)
        inv.switch_to_farming_outfit = lambda: calls.append("farm_loadout")
        pest._plots_to_clear = lambda: []
        try:
            pest.pest_cycle()
        finally:
            inv.switch_to_farming_outfit, pest._plots_to_clear = orig
        self.assertEqual(calls, [])


class PestCooldownTests(unittest.TestCase):
    def test_parse_matches_real_skyhanni_text(self):
        import farm.recovery as rec

        msg = "[SkyHanni] §cPest spawn cooldown expires in 5s\n§e[CLICK to disable this feature]"
        self.assertEqual(rec.parse_pest_cooldown(msg), 5)
        self.assertEqual(rec.parse_pest_cooldown("Pest spawn cooldown expires in 1s"), 1)
        self.assertIsNone(rec.parse_pest_cooldown("hello"))

    def test_trigger_at_5s_and_dedupes(self):
        import farm.recovery as rec

        state.clear_events()
        state.is_running = True
        state.cycling_pests = state.spraying_plots = state.flying_to_start = False
        state.last_cooldown_event_time = 0
        try:
            self.assertTrue(rec.check_for_pest_cooldown_message("Pest spawn cooldown expires in 5s"))
            self.assertEqual(state.poll_event(), "PEST_COOLDOWN")
            self.assertFalse(rec.check_for_pest_cooldown_message("Pest spawn cooldown expires in 4s"))
        finally:
            state.is_running = False


class PestFastPathTests(unittest.TestCase):
    def setUp(self):
        state.pest_alive_hint = 0
        state.pending_pest_plots.clear()
        state.last_pest_spawn_time = 0
        state.is_running = True
        state.cycling_pests = False
        state.clear_events()

    def tearDown(self):
        state.is_running = False
        state.pest_alive_hint = 0
        state.pending_pest_plots.clear()

    def test_messages_close_together_both_recorded(self):
        import farm.recovery as rec

        rec.check_for_pest_spawn_message("YUCK! 3 Pest have spawned in Plot - 4!")
        rec.check_for_pest_spawn_message("YUCK! 2 Pest have spawned in Plot - 12!")  # <5s: ไม่ส่ง event ซ้ำ แต่ต้องเก็บข้อมูล
        self.assertEqual(state.pest_alive_hint, 5)
        self.assertEqual(state.pending_pest_plots, {"4", "12"})
        self.assertEqual(state.poll_event(), "PEST_SPAWNED")
        self.assertIsNone(state.poll_event())

    def test_plots_to_clear_uses_messages_without_tablist(self):
        import farm.pest as pest

        state.pending_pest_plots.update({"12", "4"})
        called = []
        orig = pest.get_pest_info
        pest.get_pest_info = lambda: called.append(1) or (0, [])
        try:
            self.assertEqual(pest._plots_to_clear(), ["4", "12"])
            self.assertEqual(called, [])        # ไม่ได้อ่าน tablist ที่ช้า
        finally:
            pest.get_pest_info = orig

    def test_estimate_uses_hint(self):
        import farm.farm_loop as fl

        state.pest_alive_hint = 6
        self.assertGreaterEqual(fl._pests_alive_estimate(), 6)


class SensorsTests(unittest.TestCase):
    def test_pest_info_wait_times_out_without_blocking(self):
        from farm import sensors

        t0 = time.time()
        self.assertEqual(sensors.pest_info_wait(timeout=0.2), (0, []))
        self.assertLess(time.time() - t0, 0.6)

    def test_pest_info_wait_returns_fresh_value(self):
        from farm import sensors

        orig = (sensors._pest, sensors._pest_t)
        try:
            import threading

            def publish():
                time.sleep(0.1)
                sensors._pest = (3, ["4"])
                sensors._pest_t = time.time()

            threading.Thread(target=publish).start()
            self.assertEqual(sensors.pest_info_wait(timeout=1.0), (3, ["4"]))
        finally:
            sensors._pest, sensors._pest_t = orig


class BuffScheduleTests(unittest.TestCase):
    def setUp(self):
        import farm.farm_loop as fl

        self.fl = fl
        fl.BUFF_EVERY_SECONDS = 1810

    def test_buff_not_stackable_until_expired(self):
        state.last_buff_time = 0
        self.assertTrue(self.fl._buff_due())                     # ยังไม่เคยรับ
        state.last_buff_time = time.time()
        self.assertFalse(self.fl._buff_due())                    # เพิ่งรับ
        state.last_buff_time = time.time() - 1500
        self.assertFalse(self.fl._buff_due())                    # 25 นาที ยังไม่หมด
        state.last_buff_time = time.time() - 1811
        self.assertTrue(self.fl._buff_due())                     # หมดแล้ว

    def test_disabled(self):
        self.fl.BUFF_EVERY_SECONDS = 0
        state.last_buff_time = 0
        self.assertFalse(self.fl._buff_due())

    def test_independent_from_spray(self):
        self.fl.SPRAY_EVERY_SECONDS = 3300
        profile = {"spray_plots": [4]}
        state.last_buff_time = time.time() - 1811     # บัฟหมด
        state.last_spray_time = time.time()           # spray ยังอยู่
        self.assertTrue(self.fl._buff_due())
        self.assertFalse(self.fl._spray_due(profile))


class SprayScheduleTests(unittest.TestCase):
    def setUp(self):
        import farm.farm_loop as fl

        self.fl = fl
        self.profile = {"spray_plots": [4], "spray_interval": 5}

    def test_time_based(self):
        self.fl.SPRAY_EVERY_SECONDS = 3600
        state.last_spray_time = 0
        self.assertTrue(self.fl._spray_due(self.profile))        # ยังไม่เคยสเปรย์
        state.last_spray_time = time.time()
        self.assertFalse(self.fl._spray_due(self.profile))       # เพิ่งสเปรย์
        state.last_spray_time = time.time() - 3601
        self.assertTrue(self.fl._spray_due(self.profile))        # ครบเวลา

    def test_round_based_fallback(self):
        self.fl.SPRAY_EVERY_SECONDS = 0
        state.round_count = 10
        self.assertTrue(self.fl._spray_due(self.profile))
        state.round_count = 11
        self.assertFalse(self.fl._spray_due(self.profile))

    def test_no_plots_never_sprays(self):
        self.fl.SPRAY_EVERY_SECONDS = 3600
        state.last_spray_time = 0
        self.assertFalse(self.fl._spray_due({"spray_plots": []}))


if __name__ == "__main__":
    unittest.main()
