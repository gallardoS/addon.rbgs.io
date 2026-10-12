"""Exercise diagnostic actions with Lua 5.1 and a synthetic WoW UI adapter.

Requires lupa (Lua 5.1 module) in the test runtime, not in the addon/client.
"""

from pathlib import Path
import importlib.util
import json
import unittest

from lupa.lua51 import LuaRuntime


MOCK_WOW = r'''
UIObjects = {}
UIFrames = {}
UISpecialFrames = {}
SlashCmdList = {}
GameFontNormal = {}
local methods = {}
local function object(kind, name, parent)
    local item = setmetatable({kind=kind, name=name, parent=parent, scripts={}, shown=true,
        width=1024, height=768, scroll=0, enabled=true}, {__index=methods})
    UIObjects[#UIObjects + 1] = item
    if name then _G[name] = item end
    return item
end
function methods:SetScript(event, action) self.scripts[event] = action end
function methods:RegisterEvent(event)
    if event == "PLAYER_PVP_MATCH_COMPLETE" then error("Unsupported fixture event") end
    self.events=self.events or {}
    self.events[event]=true
end
function methods:SetSize(width, height) self.width=width; self.height=height end
function methods:SetWidth(width) self.width=width end
function methods:SetHeight(height) self.height=height end
function methods:GetWidth() return self.width end
function methods:GetHeight() return self.height end
function methods:SetPoint(...) self.point={...} end
function methods:ClearAllPoints() self.point=nil end
function methods:SetAllPoints() end
function methods:SetColorTexture(...) self.color={...} end
function methods:SetTexture(path) self.texture=path end
function methods:SetBlendMode(mode) self.blendMode=mode end
function methods:SetTextColor(...) self.textColor={...} end
function methods:SetJustifyH() end
function methods:SetJustifyV() end
function methods:SetFrameStrata(value) self.strata=value end
function methods:SetFrameLevel(value) self.level=value end
function methods:GetFrameLevel() return self.level or 1 end
function methods:RegisterForClicks(...) self.clicks={...} end
function methods:SetHighlightTexture(value) self.highlight=value end
function methods:GetCenter() return 100, 100 end
function methods:GetEffectiveScale() return 1 end
function methods:SetClampedToScreen() end
function methods:SetMovable() end
function methods:EnableMouse(value) self.mouseEnabled=value end
function methods:RegisterForDrag(...) self.dragButtons={...} end
function methods:StartMoving() end
function methods:StopMovingOrSizing() end
function methods:SetScale(scale) self.scale=scale end
function methods:SetEnabled(enabled) self.enabled=enabled end
function methods:SetAlpha(alpha) self.alpha=alpha end
function methods:EnableMouseWheel() end
function methods:SetScrollChild(child) self.child=child end
function methods:GetVerticalScroll() return self.scroll end
function methods:GetVerticalScrollRange() return math.max(0, self.child.height - self.height) end
function methods:SetVerticalScroll(offset) self.scroll=offset end
function methods:SetText(value) self.text=value end
function methods:GetStringHeight()
    local _, lines = (self.text or ""):gsub("\n", "\n")
    return (lines + 1) * 16
end
function methods:IsShown() return self.shown end
function methods:Hide() self.shown=false end
function methods:Show()
    local changed=not self.shown
    self.shown=true
    if changed and self.scripts.OnShow then self.scripts.OnShow(self) end
end
function methods:CreateTexture(name) return object("Texture", name, self) end
function methods:CreateFontString(name) return object("FontString", name, self) end
UIParent = object("Frame", "UIParent")
Minimap = object("Frame", "Minimap", UIParent)
function CreateFrame(kind, name, parent)
    local item=object(kind, name, parent)
    UIFrames[#UIFrames + 1] = item
    return item
end
DEFAULT_CHAT_FRAME = {AddMessage=function() end}
function GetServerTime() return 100 end
function GetBuildInfo() return "1.60.1", "70291", "fixture-date", 16001 end
function GetInstanceInfo() return "Darkspear Islands", FixtureInstanceType or "none" end
function GetRealmName() return "Fixture Realm" end
function UnitName(unit) return unit == "player" and "FixturePlayer" or "FixtureTeammate" end
function UnitGUID() return "fixture-guid" end
function GetNumGroupMembers() return 0 end
function GetNumSubgroupMembers() return 0 end
function GetNumBattlefieldScores() return FixtureScoreCount or 0 end
function GetBattlefieldScore(index) return "FixturePlayer", 4, nil, 0 end
function GetBattlefieldWinner() return FixtureWinner end
function RequestBattlefieldScoreData() end
function InCombatLockdown() return FixtureCombat or false end
function ReloadUI() FixtureReloaded=true end
function date() return "12:00:00" end
function loadAddon(source, namespace)
    assert(loadstring(source))("RBGSCompatibility", namespace)
end
function click(control)
    if control.name == "RBGSProbeLauncher" then
        assert(control.mouseEnabled and control.clicks and control.clicks[1] == "LeftButtonUp")
    end
    control.scripts.OnClick(control)
end
function GetCursorPosition() return FixtureCursorX or 180, FixtureCursorY or 100 end
function fire(event, ...)
    for _, widget in ipairs(UIFrames) do
        if widget.events and widget.events[event] and widget.scripts.OnEvent then
            widget.scripts.OnEvent(widget, event, ...)
        end
    end
end
function tick(seconds)
    for _, widget in ipairs(UIFrames) do
        if widget.scripts.OnUpdate then widget.scripts.OnUpdate(widget, seconds) end
    end
end
function visibleText()
    local output={}
    for _, item in ipairs(UIObjects) do
        if item.kind == "FontString" and item.text then output[#output + 1]=item.text end
    end
    return table.concat(output, "\n")
end
'''


class ProbePanelTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCK_WOW)
        self.namespace = self.lua.table()
        root = Path(__file__).resolve().parents[1] / "RBGSCompatibility"
        loader = self.lua.globals().loadAddon
        for file in ("RBGSCompatibility.lua", "ProbePanel.lua"):
            loader((root / file).read_text(encoding="utf-8"), self.namespace)
        self.lua.execute('fire("ADDON_LOADED", "RBGSCompatibility"); fire("PLAYER_LOGIN")')

    def test_panel_opens_at_login_and_launcher_reopens_it(self):
        launcher = self.lua.globals().RBGSProbeLauncher
        self.assertTrue(self.lua.eval('RBGSProbeLauncher.parent == Minimap'))
        self.assertEqual(launcher.width, 31)
        self.assertEqual(launcher.strata, "HIGH")
        self.assertTrue(self.lua.globals().RBGSProbePanel.shown)
        self.lua.execute('click(RBGSProbeClose)')
        self.assertFalse(self.lua.globals().RBGSProbePanel.shown)
        self.lua.execute('click(RBGSProbeLauncher)')
        self.assertTrue(self.lua.globals().RBGSProbePanel.shown)
        self.assertIn("RBGSProbePanel", list(self.lua.globals().UISpecialFrames.values()))

    def test_minimap_drag_keeps_button_on_rim_and_restores_saved_angle(self):
        self.lua.execute('RBGSProbeLauncher.scripts.OnDragStart(RBGSProbeLauncher); tick(0.1)')
        self.assertAlmostEqual(self.lua.globals().RBGSDebuggerSettings.minimapAngle, 0)
        self.lua.execute('RBGSProbeLauncher.scripts.OnDragStop(RBGSProbeLauncher)')
        self.assertIsNone(self.lua.globals().RBGSProbeLauncher.scripts.OnUpdate)
        self.lua.execute('RBGSDebuggerSettings.minimapAngle=90; fire("PLAYER_LOGIN")')
        launcher = self.lua.globals().RBGSProbeLauncher
        self.assertAlmostEqual(launcher.point[4], 0, places=5)
        self.assertGreater(launcher.point[5], 0)

    def test_manual_diagnostic_capture_remains_available_without_phase_buttons(self):
        self.lua.execute('FixtureScoreCount=1; FixtureWinner=0')
        for phase in ("Before BG", "During BG", "Final result"):
            self.namespace.CaptureSnapshot(phase)
            latest, _ = self.namespace.LatestRecords()
            self.assertEqual(latest.capture_marker.payload.phase, phase)
            self.assertEqual(latest.scoreboard.payload.count, 1)
            self.assertEqual(latest.scoreboard.payload.winner[1], "0")
        rendered = self.lua.globals().visibleText()
        self.assertIn("Darkspear Islands", rendered)
        self.assertIn("RAW WINNER (UNVERIFIED)", rendered)
        self.assertIn("3=Unknown, 4=0", rendered)
        for phase in ("Before BG", "During BG", "Final result"):
            self.assertIn(phase, rendered)
        for control in ("RBGSProbeBefore", "RBGSProbeDuring", "RBGSProbeFinal", "RBGSProbeCapabilities"):
            self.assertIsNone(self.lua.globals()[control])

    def test_missing_winner_and_failing_score_api_do_not_fabricate_results(self):
        self.lua.execute('GetNumBattlefieldScores=function() error("fixture API unavailable") end; GetBattlefieldWinner=nil')
        self.namespace.CaptureSnapshot("Final result")
        latest, _ = self.namespace.LatestRecords()
        self.assertEqual(latest.scoreboard.payload.winnerError, "missing")
        rendered = self.lua.globals().visibleText()
        self.assertIn("Unavailable", rendered)
        self.assertIn("Unknown", rendered)
        self.assertNotIn("Victory", rendered)

    def test_reload_requires_click_and_is_blocked_in_combat(self):
        self.assertIsNone(self.lua.globals().FixtureReloaded)
        self.lua.execute('FixtureCombat=true; click(RBGSProbeReload)')
        self.assertIsNone(self.lua.globals().FixtureReloaded)
        self.lua.execute('FixtureCombat=false; click(RBGSProbeReload)')
        self.assertTrue(self.lua.globals().FixtureReloaded)

    def test_capability_check_and_bounded_history_preserve_existing_records(self):
        self.lua.execute('SlashCmdList.RBGSPROBE("capabilities")')
        latest, _ = self.namespace.LatestRecords()
        self.assertEqual(latest.capabilities.payload.GetBattlefieldWinner, "function")
        for _ in range(80):
            self.namespace.CaptureSnapshot("Before BG")
        _, count = self.namespace.LatestRecords()
        self.assertEqual(count, 300)

    def test_saved_markers_restore_and_commands_still_capture(self):
        self.lua.execute('RBGSCompatibilityData.records[1]={kind="capture_marker", at=50, payload={phase="Restored fixture"}}; fire("ADDON_LOADED", "RBGSCompatibility")')
        rendered = self.lua.globals().visibleText()
        self.assertIn("Restored fixture", rendered)
        self.lua.execute('SlashCmdList.RBGSPROBE("capture")')
        latest, _ = self.namespace.LatestRecords()
        self.assertEqual(latest.capture_marker.payload.phase, "Manual")

    def test_capture_serializes_through_the_companion_parser_and_restores(self):
        self.lua.execute('FixtureInstanceType="pvp"; fire("PLAYER_ENTERING_WORLD"); FixtureScoreCount=1; FixtureWinner=0; fire("PVP_MATCH_COMPLETE")')

        def encode(value):
            if isinstance(value, str):
                return json.dumps(value)
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, (int, float)):
                return str(value)
            return "{" + ",".join(f"[{encode(key)}]={encode(item)}" for key, item in value.items()) + "}"

        source = "RBGSCompatibilityData = " + encode(self.lua.globals().RBGSCompatibilityData)
        parser_path = Path(__file__).resolve().parents[2] / "companion.rbgs.io/tools/parse_probe.py"
        if not parser_path.is_file():
            self.skipTest("Optional integration requires the companion repository alongside this addon repository")
        spec = importlib.util.spec_from_file_location("fixture_probe_parser", parser_path)
        parser = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parser)
        parsed = parser.parse(source)
        self.assertEqual(parsed["schema"], 1)
        self.assertEqual(parsed["records"][-1]["payload"]["phase"], "Automatic final result")
        self.lua.execute(source)
        self.lua.execute('fire("ADDON_LOADED", "RBGSCompatibility"); fire("PLAYER_LOGIN")')
        self.assertIn("Automatic final result", self.lua.globals().visibleText())

    def test_five_minute_poll_detects_result_when_completion_event_is_missed(self):
        self.lua.execute('FixtureInstanceType="pvp"; fire("PLAYER_ENTERING_WORLD"); FixtureScoreCount=30; FixtureWinner=0; tick(300)')
        latest, _ = self.namespace.LatestRecords()
        self.assertEqual(latest.capture_marker.payload.phase, "Automatic final result")
        self.assertEqual(latest.scoreboard.payload.winner[1], "0")

    def test_automatic_entry_and_five_minute_capture_ignore_event_storms(self):
        self.lua.execute('FixtureInstanceType="pvp"; fire("PLAYER_ENTERING_WORLD")')
        latest, initial_count = self.namespace.LatestRecords()
        self.assertEqual(latest.capture_marker.payload.phase, "Automatic BG entry")
        self.lua.execute('for i=1,500 do fire("UPDATE_BATTLEFIELD_SCORE"); fire("GROUP_ROSTER_UPDATE"); fire("UPDATE_BATTLEFIELD_STATUS") end; tick(299)')
        self.assertEqual(self.namespace.LatestRecords()[1], initial_count)
        self.lua.execute('tick(1)')
        latest, count = self.namespace.LatestRecords()
        self.assertEqual(count, initial_count + 5)
        self.assertEqual(latest.capture_marker.payload.phase, "Automatic 5-minute capture")
        self.assertIsNone(self.lua.globals().FixtureReloaded)

    def test_final_result_bypasses_interval_and_retries_delayed_zero_winner(self):
        self.lua.execute('FixtureInstanceType="pvp"; fire("PLAYER_ENTERING_WORLD"); tick(10); fire("PVP_MATCH_COMPLETE")')
        latest, count = self.namespace.LatestRecords()
        self.assertEqual(latest.capture_marker.payload.phase, "Automatic final result")
        self.lua.execute('FixtureScoreCount=30; FixtureWinner=0; tick(2)')
        latest, ready_count = self.namespace.LatestRecords()
        self.assertEqual(ready_count, count + 2)
        self.assertEqual(latest.capture_marker.payload.phase, "Automatic final result ready")
        self.assertEqual(latest.scoreboard.payload.count, 30)
        self.assertEqual(latest.scoreboard.payload.winner[1], "0")
        self.lua.execute('for i=1,500 do fire("UPDATE_BATTLEFIELD_SCORE"); fire("PVP_MATCH_COMPLETE") end; tick(600)')
        self.assertEqual(self.namespace.LatestRecords()[1], ready_count)

    def test_unavailable_final_result_has_bounded_retries(self):
        self.lua.execute('FixtureInstanceType="pvp"; fire("PLAYER_ENTERING_WORLD"); fire("PVP_MATCH_COMPLETE"); tick(29)')
        _, count = self.namespace.LatestRecords()
        self.lua.execute('tick(1)')
        latest, timeout_count = self.namespace.LatestRecords()
        self.assertEqual(timeout_count, count + 2)
        self.assertEqual(latest.capture_marker.payload.phase, "Automatic final result unavailable")
        self.assertEqual(latest.scoreboard.payload.winner[1], "<nil or protected>")
        self.lua.execute('tick(600)')
        self.assertEqual(self.namespace.LatestRecords()[1], timeout_count)

    def test_periodic_capture_stops_outside_bg_and_restarts_on_next_entry(self):
        _, initial = self.namespace.LatestRecords()
        self.lua.execute('tick(600)')
        self.assertEqual(self.namespace.LatestRecords()[1], initial)
        self.lua.execute('FixtureInstanceType="pvp"; fire("PLAYER_ENTERING_WORLD"); tick(299); FixtureInstanceType="none"; fire("ZONE_CHANGED_NEW_AREA")')
        _, outside = self.namespace.LatestRecords()
        self.lua.execute('tick(600)')
        self.assertEqual(self.namespace.LatestRecords()[1], outside)
        self.lua.execute('FixtureInstanceType="pvp"; fire("ZONE_CHANGED_NEW_AREA"); tick(1)')
        latest, _ = self.namespace.LatestRecords()
        self.assertEqual(latest.capture_marker.payload.phase, "Automatic BG entry")

    def test_final_result_available_immediately_stops_periodic_captures(self):
        self.lua.execute('FixtureInstanceType="pvp"; fire("PLAYER_ENTERING_WORLD"); FixtureScoreCount=30; FixtureWinner=0; fire("PVP_MATCH_COMPLETE")')
        latest, count = self.namespace.LatestRecords()
        self.assertEqual(latest.scoreboard.payload.winner[1], "0")
        self.lua.execute('tick(600)')
        self.assertEqual(self.namespace.LatestRecords()[1], count)

    def test_clear_history_requires_click_and_out_of_combat_reload(self):
        _, count = self.namespace.LatestRecords()
        self.lua.execute('FixtureCombat=true; click(RBGSProbeClear)')
        self.assertEqual(self.namespace.LatestRecords()[1], count)
        self.assertIsNone(self.lua.globals().FixtureReloaded)
        self.lua.execute('FixtureCombat=false; click(RBGSProbeClear)')
        self.assertEqual(self.namespace.LatestRecords()[1], 0)
        self.assertTrue(self.lua.globals().FixtureReloaded)

    def test_clear_preserves_history_if_reload_is_missing_or_fails(self):
        _, count = self.namespace.LatestRecords()
        self.lua.execute('ReloadUI=nil; click(RBGSProbeClear)')
        self.assertEqual(self.namespace.LatestRecords()[1], count)
        self.lua.execute('ReloadUI=function() error("fixture reload failure") end; click(RBGSProbeClear)')
        self.assertEqual(self.namespace.LatestRecords()[1], count)


if __name__ == "__main__":
    unittest.main()
