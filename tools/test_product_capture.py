"""Production capture isolation and bounded persistence, using Lua 5.1 fixtures."""
import copy
import json
import os
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime
from test_probe_panel import MOCK_WOW

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "RB2:00000000-0000-4000-8000-000000000003:0123456789ABCDEF"
TOKEN2 = "RB2:00000000-0000-4000-8000-000000000004:0123456789ABCDEG"
API = r'''
FixtureInstanceType="none"
FixtureWinner=nil
FixtureScoreCount=0
FixtureNow=1791734400
function GetServerTime() return FixtureNow end
function GetBuildInfo() return "1.60.1", FixtureBuild or "70338", "fixture", 16001 end
function date() return "2026-10-11T16:00:00Z" end
function GetInstanceInfo() return FixtureMapName or "Darkspear Islands", FixtureInstanceType, nil, nil, nil, nil, nil, FixtureMapId or 2997 end
function UnitName() return FixtureCharacter or "SyntheticHorde", FixtureSurname or "FixtureSurname" end
function GetBattlefieldScore(index)
    if FixtureBadRow then return nil end
    return index == 1 and "SyntheticHorde FixtureSurname-Fixture Realm" or "SyntheticAlliance OtherSurname-Other Realm",
        8, FixtureUnknownHK and nil or 63, 2, 100, index == 1 and 0 or 1, "unused", "unused", "unused", 31097, 0
end
function command(value) SlashCmdList.RBGS(value) end
function loadProduct(source, ns) assert(loadstring(source))("RBGS", ns) end
Messages={}
DEFAULT_CHAT_FRAME={AddMessage=function(_, message) Messages[#Messages+1]=message end}
'''


def data(value):
    if hasattr(value, "items"):
        items = dict(value.items())
        if items and all(isinstance(key, int) for key in items):
            return [data(items[i]) for i in range(1, len(items) + 1)]
        return {key: data(item) for key, item in items.items()}
    return value


def json_envelope(root):
    """Explicit Lua-nil -> JSON-null mapping required of the future reader."""
    result = copy.deepcopy(root)
    if result["captures"] == {}:
        result["captures"] = []
    for item in result["captures"]:
        item["observedCharacter"].setdefault("realm", None)
        capture = item["capture"]
        for key in ("map", "startedAt", "endedAt", "incompleteReason"):
            capture.setdefault(key, None)
        if capture["roster"] == {}:
            capture["roster"] = []
        if capture["map"]:
            capture["map"].setdefault("gameMapId", None)
        capture["outcome"].setdefault("winningObservedTeamKey", None)
        for row in capture["roster"]:
            row["character"].setdefault("realm", None)
            row.setdefault("observedTeamKey", None)
    return result


class ProductCaptureTests(unittest.TestCase):
    def setUp(self):
        self.boot()

    def boot(self, saved=None, settings=None, setup=""):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCK_WOW)
        self.lua.execute(API)
        self.lua.execute(setup)
        if saved is not None or settings is not None:
            def table(value):
                if isinstance(value, list):
                    return self.lua.table_from([table(item) for item in value])
                if isinstance(value, dict):
                    return self.lua.table_from({key: table(item) for key, item in value.items()})
                return value
            if saved is not None:
                self.lua.globals().RBGSMatchData = table(saved)
            if settings is not None:
                self.lua.globals().RBGSSettings = table(settings)
        self.app = self.lua.table()
        for name in ("CaptureStore.lua", "ForeverAdapter.lua", "RBGS.lua", "Panel.lua", "ScoreboardButton.lua"):
            self.lua.globals().loadProduct((ROOT / "RBGS" / name).read_text(encoding="utf-8"), self.app)
        self.lua.execute('fire("ADDON_LOADED", "RBGS"); fire("PLAYER_LOGIN")')

    def command(self, value):
        self.lua.globals().command(value)

    def arm(self, token=TOKEN):
        self.command("match " + token)

    def saved(self):
        return data(self.lua.globals().RBGSMatchData)

    def last(self):
        return self.saved()["captures"][-1]

    def enter(self):
        self.lua.execute('FixtureInstanceType="pvp"; fire("PLAYER_ENTERING_WORLD")')

    def finish(self, winner=1):
        self.lua.execute(f'fire("PVP_MATCH_COMPLETE"); FixtureWinner={winner}; FixtureScoreCount=2; fire("UPDATE_BATTLEFIELD_SCORE")')

    def test_arm_validates_bounded_token_and_does_not_log_secret(self):
        for token in ("", TOKEN + "x", TOKEN.replace("RB2", "rb2"), TOKEN.replace("ABCDEF", "ABCDEI"), "return os.execute('bad')"):
            self.arm(token)
            self.assertEqual(self.saved()["captures"], {})
        self.arm()
        self.assertEqual(self.last()["captureRevision"], 1)
        self.assertEqual(self.last()["capture"]["stage"], "ARMED")
        self.command("status")
        self.assertNotIn("0123456789ABCDEF", "\n".join(self.lua.globals().Messages.values()))

    def scoreboard(self):
        self.lua.execute('''PVPMatchResults=CreateFrame("Frame", "PVPMatchResults", UIParent)
            PVPMatchResults.leaveButton=CreateFrame("Button", "FixtureLeaveMatch", PVPMatchResults)
            PVPMatchResults.leaveButton:SetSize(168, 20)
            PVPMatchResults.leaveButton:SetScript("OnClick", function() FixtureLeft=true end)
            function PVPMatchResults:BeginShow() FixtureBeginShow=(FixtureBeginShow or 0)+1; self:Show() end''')

    def test_scoreboard_button_waits_for_final_data_then_saves_with_user_click(self):
        self.arm(); self.enter(); self.scoreboard()
        self.lua.execute('FixtureWinner=1; fire("PVP_MATCH_COMPLETE"); tick(0.5)')
        button = self.lua.globals().RBGSScoreboardSaveResults
        self.assertTrue(button.shown)
        self.assertFalse(button.enabled)
        self.assertFalse(self.lua.globals().FixtureLeaveMatch.shown)
        self.lua.execute('click(RBGSScoreboardSaveResults)')
        self.assertFalse(bool(self.lua.globals().FixtureReloaded))
        self.lua.execute('FixtureScoreCount=2; fire("UPDATE_BATTLEFIELD_SCORE"); tick(0.5)')
        self.assertTrue(button.enabled)
        self.assertEqual(button.text, "rbgs.io: Save results")
        self.assertEqual(button.point[1], "CENTER")
        before = self.saved()
        self.lua.execute('click(RBGSScoreboardSaveResults)')
        self.assertTrue(self.lua.globals().FixtureReloaded)
        self.assertEqual(self.saved(), before)
        self.assertFalse(button.enabled)

    def test_scoreboard_save_rechecks_combat_and_never_uses_an_old_match(self):
        self.arm(); self.enter(); self.scoreboard(); self.finish()
        self.lua.execute('tick(0.5); FixtureCombat=true; click(RBGSScoreboardSaveResults)')
        self.assertFalse(bool(self.lua.globals().FixtureReloaded))
        self.lua.execute('FixtureCombat=false; FixtureInstanceType="none"; fire("PLAYER_ENTERING_WORLD"); FixtureInstanceType="pvp"; fire("PLAYER_ENTERING_WORLD"); tick(0.5)')
        self.assertFalse(self.lua.globals().RBGSScoreboardSaveResults.shown)
        self.lua.execute('click(RBGSScoreboardSaveResults)')
        self.assertFalse(bool(self.lua.globals().FixtureReloaded))

    def test_scoreboard_ui_can_load_late_and_missing_ui_keeps_manual_reload(self):
        self.arm(); self.enter(); self.finish()
        self.lua.execute('tick(0.5)')
        self.assertIsNone(self.lua.globals().RBGSScoreboardSaveResults)
        self.scoreboard(); self.lua.execute('tick(0.5)')
        self.assertTrue(self.lua.globals().RBGSScoreboardSaveResults.enabled)
        self.lua.execute('PVPMatchResults:Hide(); tick(0.5)')
        self.assertFalse(self.lua.globals().RBGSScoreboardSaveResults.shown)
        self.command('reload')
        self.assertTrue(self.lua.globals().FixtureReloaded)

    def test_scoreboard_classic_fallback_and_reload_do_not_offer_old_results(self):
        self.arm(); self.enter(); self.finish()
        self.lua.execute('WorldStateScoreFrame=CreateFrame("Frame", "WorldStateScoreFrame", UIParent); WorldStateScoreFrameLeaveButton=CreateFrame("Button", "WorldStateScoreFrameLeaveButton", WorldStateScoreFrame); tick(0.5)')
        self.assertTrue(self.lua.globals().RBGSScoreboardSaveResults.enabled)
        saved = self.saved()
        self.boot(saved)
        self.scoreboard()
        self.lua.execute('FixtureInstanceType="pvp"; FixtureWinner=1; fire("PLAYER_ENTERING_WORLD"); tick(0.5)')
        self.assertIsNone(self.lua.globals().RBGSScoreboardSaveResults)
        self.assertEqual(self.saved(), saved)

    def saved_scoreboard_reload(self):
        self.arm(); self.enter(); self.scoreboard(); self.finish()
        self.lua.execute('RBGSSettings.minimapAngle=42; click(RBGSScoreboardSaveResults)')
        return self.saved(), data(self.lua.globals().RBGSSettings)

    def reload_world(self):
        self.lua.execute('FixtureInstanceType="pvp"; FixtureWinner=1; FixtureScoreCount=2; fire("PLAYER_ENTERING_WORLD", false, true); tick(0.5)')

    def test_reload_reopens_scoreboard_once_with_only_the_original_exit(self):
        saved, settings = self.saved_scoreboard_reload()
        self.assertNotIn("assignmentCode", settings["reopenResults"])
        self.boot(saved, settings)
        self.scoreboard()
        self.lua.execute('PVPMatchResults:Hide(); function LeaveBattlefield() error("must never leave automatically") end')
        self.reload_world()
        self.assertTrue(self.lua.globals().PVPMatchResults.shown)
        self.assertTrue(self.lua.globals().FixtureLeaveMatch.shown)
        self.assertIsNone(self.lua.globals().RBGSScoreboardSaveResults)
        self.assertEqual(self.lua.globals().FixtureBeginShow, 1)
        self.assertIsNone(self.lua.globals().RBGSSettings.reopenResults)
        self.assertEqual(self.lua.globals().RBGSSettings.minimapAngle, 42)
        self.assertEqual(self.saved(), saved)
        self.lua.execute('PVPMatchResults:Hide(); tick(2)')
        self.assertFalse(self.lua.globals().PVPMatchResults.shown)
        self.lua.execute('PVPMatchResults:Show(); click(FixtureLeaveMatch)')
        self.assertTrue(self.lua.globals().FixtureLeft)

    def test_native_exit_stays_hidden_when_blizzard_shows_it_again(self):
        self.arm(); self.enter(); self.scoreboard(); self.finish()
        self.lua.execute('FixtureLeaveMatch:Show()')
        self.assertFalse(self.lua.globals().FixtureLeaveMatch.shown)
        self.assertTrue(self.lua.globals().RBGSScoreboardSaveResults.shown)
        self.lua.execute('PVPMatchResults:Hide()')
        self.assertTrue(self.lua.globals().FixtureLeaveMatch.shown)
        self.lua.execute('PVPMatchResults:Show()')
        self.assertFalse(self.lua.globals().FixtureLeaveMatch.shown)

    def test_unassigned_scoreboard_and_combat_keep_the_original_exit(self):
        self.scoreboard(); self.lua.execute('tick(0.5)')
        self.assertTrue(self.lua.globals().FixtureLeaveMatch.shown)
        self.assertIsNone(self.lua.globals().RBGSScoreboardSaveResults)
        self.arm(); self.enter(); self.finish()
        self.lua.execute('FixtureCombat=true; tick(0.5)')
        self.assertTrue(self.lua.globals().FixtureLeaveMatch.shown)
        self.assertFalse(self.lua.globals().RBGSScoreboardSaveResults.shown)
        self.lua.execute('FixtureCombat=false; tick(0.5)')
        self.assertFalse(self.lua.globals().FixtureLeaveMatch.shown)

    def test_failed_or_silent_reload_restores_exit_and_discards_reopen_intent(self):
        for failure in ('ReloadUI=function() error("blocked") end', 'ReloadUI=function() end'):
            with self.subTest(failure=failure):
                self.boot(); self.arm(); self.enter(); self.scoreboard(); self.finish()
                self.lua.execute(failure + '; click(RBGSScoreboardSaveResults); tick(11)')
                self.assertTrue(self.lua.globals().FixtureLeaveMatch.shown)
                self.assertFalse(self.lua.globals().RBGSScoreboardSaveResults.shown)
                self.assertIsNone(self.lua.globals().RBGSSettings.reopenResults)
                self.lua.execute('FixtureLeaveMatch:Show(); tick(1)')
                self.assertTrue(self.lua.globals().FixtureLeaveMatch.shown)

    def test_reopen_waits_for_scores_and_late_native_ui(self):
        saved, settings = self.saved_scoreboard_reload()
        self.boot(saved, settings)
        self.lua.execute('FixtureInstanceType="pvp"; fire("PLAYER_ENTERING_WORLD", false, true); tick(0.5)')
        self.assertIsNone(self.lua.globals().FixtureBeginShow)
        self.scoreboard(); self.lua.execute('PVPMatchResults:Hide(); tick(0.5)')
        self.assertFalse(self.lua.globals().PVPMatchResults.shown)
        self.lua.execute('FixtureWinner=1; FixtureScoreCount=2; tick(0.5)')
        self.assertTrue(self.lua.globals().PVPMatchResults.shown)

    def test_reopen_loads_native_module_and_waits_for_temporarily_unknown_identity(self):
        saved, settings = self.saved_scoreboard_reload()
        self.boot(saved, settings)
        self.lua.execute('''local original=GetInstanceInfo
            function UIParentLoadAddOn(name)
                assert(name=="Blizzard_PVPMatch")
                FixtureModuleLoads=(FixtureModuleLoads or 0)+1
                PVPMatchResults=CreateFrame("Frame", "PVPMatchResults", UIParent)
                PVPMatchResults.leaveButton=CreateFrame("Button", "FixtureLeaveMatch", PVPMatchResults)
                PVPMatchResults:Hide()
                function PVPMatchResults:BeginShow() FixtureBeginShow=(FixtureBeginShow or 0)+1; self:Show() end
            end
            local originalName=UnitName
            function UnitName() return nil end
            FixtureInstanceType="pvp"; FixtureWinner=1; FixtureScoreCount=2
            fire("PLAYER_ENTERING_WORLD", false, true); tick(0.5)
            UnitName=originalName''')
        self.assertIsNone(self.lua.globals().PVPMatchResults)
        self.lua.execute('tick(0.5)')
        self.assertTrue(self.lua.globals().PVPMatchResults.shown)
        self.assertEqual(self.lua.globals().FixtureModuleLoads, 1)

    def test_reopen_times_out_without_reopening_on_later_updates(self):
        saved, settings = self.saved_scoreboard_reload()
        self.boot(saved, settings); self.scoreboard()
        self.lua.execute('PVPMatchResults:Hide(); FixtureInstanceType="pvp"; fire("PLAYER_ENTERING_WORLD", false, true); tick(16); FixtureWinner=1; FixtureScoreCount=2; tick(1)')
        self.assertFalse(self.lua.globals().PVPMatchResults.shown)
        self.assertIsNone(self.lua.globals().RBGSSettings.reopenResults)

    def test_capture_failure_restores_exit_and_ui_failure_never_hides_the_only_control(self):
        self.arm(); self.enter(); self.scoreboard()
        self.lua.execute('FixtureWinner=1; fire("PVP_MATCH_COMPLETE"); tick(0.5)')
        self.assertFalse(self.lua.globals().FixtureLeaveMatch.shown)
        self.lua.execute('tick(31)')
        self.assertTrue(self.lua.globals().FixtureLeaveMatch.shown)
        self.assertFalse(self.lua.globals().RBGSScoreboardSaveResults.shown)
        self.boot(); self.arm(); self.enter(); self.scoreboard()
        self.lua.execute('FixtureLeaveMatch.Hide=function() error("protected native control") end')
        self.finish(); self.lua.execute('tick(0.5)')
        self.assertTrue(self.lua.globals().FixtureLeaveMatch.shown)
        self.assertFalse(self.lua.globals().RBGSScoreboardSaveResults.shown)

    def test_reopen_rejects_login_expiry_wrong_game_identity_and_revision(self):
        saved, settings = self.saved_scoreboard_reload()
        cases = {
            "login": 'FixtureInstanceType="pvp"; FixtureWinner=1; FixtureScoreCount=2; fire("PLAYER_ENTERING_WORLD", true, false)',
            "missing reload flag": 'FixtureInstanceType="pvp"; FixtureWinner=1; FixtureScoreCount=2; fire("PLAYER_ENTERING_WORLD")',
            "outside": 'fire("PLAYER_ENTERING_WORLD", false, true)',
            "map": 'FixtureMapId=999; FixtureInstanceType="pvp"; FixtureWinner=1; FixtureScoreCount=2; fire("PLAYER_ENTERING_WORLD", false, true)',
            "winner": 'FixtureInstanceType="pvp"; FixtureWinner=0; FixtureScoreCount=2; fire("PLAYER_ENTERING_WORLD", false, true)',
            "identity": 'FixtureSurname="SomeoneElse"; FixtureInstanceType="pvp"; FixtureWinner=1; FixtureScoreCount=2; fire("PLAYER_ENTERING_WORLD", false, true)',
            "expiry": 'FixtureNow=FixtureNow+121; FixtureInstanceType="pvp"; FixtureWinner=1; FixtureScoreCount=2; fire("PLAYER_ENTERING_WORLD", false, true)',
        }
        for label, script in cases.items():
            with self.subTest(label=label):
                self.boot(saved, copy.deepcopy(settings)); self.scoreboard()
                self.lua.execute('PVPMatchResults:Hide(); ' + script + '; tick(1)')
                self.assertFalse(self.lua.globals().PVPMatchResults.shown)
                self.assertIsNone(self.lua.globals().RBGSSettings.reopenResults)
        stale = copy.deepcopy(settings)
        stale["reopenResults"]["revision"] += 1
        self.boot(saved, stale); self.scoreboard(); self.lua.execute('PVPMatchResults:Hide()')
        self.reload_world()
        self.assertFalse(self.lua.globals().PVPMatchResults.shown)

    def test_forever_surname_is_part_of_identity_and_realm_stays_separate(self):
        self.arm(); self.enter(); self.finish()
        identity = self.last()["observedCharacter"]
        self.assertEqual(identity["name"], "SyntheticHorde FixtureSurname")
        self.assertEqual(identity["realm"], "Fixture Realm")
        self.assertEqual(identity["name"], self.last()["capture"]["roster"][0]["character"]["name"])
        self.assertEqual(self.last()["capture"]["stage"], "COMPLETE")

    def test_surname_change_is_a_character_change_without_relabeling(self):
        for during_recording in (False, True):
            with self.subTest(during_recording=during_recording):
                self.boot(); self.arm()
                original = self.last()["observedCharacter"]
                if during_recording:
                    self.enter()
                self.lua.execute('FixtureSurname="OtherSurname"')
                if during_recording:
                    self.lua.execute('tick(3)')
                else:
                    self.enter()
                self.assertEqual(self.last()["capture"]["incompleteReason"], "CHARACTER_CHANGED")
                self.assertEqual(self.last()["observedCharacter"], original)

    def test_unknown_or_invalid_surname_cannot_arm_a_partial_identity(self):
        for surname in ('nil', '""', '{}', 'string.rep("x", 256)'):
            with self.subTest(surname=surname):
                self.boot()
                self.lua.execute('function UnitName() return "SyntheticHorde", ' + surname + ' end')
                self.arm()
                self.assertEqual(self.saved()["captures"], {})

    def test_surname_update_preserves_old_terminal_name_and_rejects_old_armed_identity(self):
        self.arm(); self.enter(); self.finish()
        old_final = self.saved()
        old_final["captures"][0]["observedCharacter"]["name"] = "SyntheticHorde"
        self.boot(old_final)
        self.assertEqual(self.saved(), old_final)
        self.boot(); self.arm()
        old_armed = self.saved()
        old_armed["captures"][0]["observedCharacter"]["name"] = "SyntheticHorde"
        self.boot(old_armed)
        self.assertEqual(self.last()["observedCharacter"]["name"], "SyntheticHorde")
        self.assertEqual(self.last()["capture"]["incompleteReason"], "CHARACTER_CHANGED")

    def test_two_games_keep_separate_frozen_final_captures(self):
        self.arm(); self.enter(); self.finish(1)
        first = self.last()
        self.lua.execute('FixtureInstanceType="none"; fire("PLAYER_ENTERING_WORLD"); FixtureWinner=nil')
        self.arm(TOKEN2); self.enter(); self.finish(0)
        self.assertEqual(len(self.saved()["captures"]), 2)
        self.assertEqual(self.saved()["captures"][0], first)
        self.assertEqual(self.last()["capture"]["outcome"]["winningObservedTeamKey"], "0")
        self.assertEqual(first["capture"]["outcome"]["winningObservedTeamKey"], "1")
        self.assertEqual(first["capture"]["roster"][0]["healing"], 0)
        self.assertNotIn("objectives", first["capture"]["roster"][0])

    def test_repeated_events_and_flushes_do_not_change_frozen_final(self):
        self.arm(); self.enter(); self.finish()
        snapshot = self.saved()
        self.lua.execute('for i=1,20 do fire("PVP_MATCH_COMPLETE"); fire("UPDATE_BATTLEFIELD_SCORE"); tick(3) end')
        self.command("reload")
        self.assertEqual(self.saved(), snapshot)
        self.assertTrue(self.lua.globals().FixtureReloaded)

    def test_reload_recording_and_final_pending_are_incomplete(self):
        for final_pending in (False, True):
            self.boot(); self.arm(); self.enter()
            if final_pending:
                self.lua.execute('fire("PVP_MATCH_COMPLETE")')
            before = self.last()
            self.boot(self.saved())
            self.lua.execute('fire("PLAYER_ENTERING_WORLD", true, false)')
            after = self.last()
            self.assertEqual(after["captureId"], before["captureId"])
            self.assertEqual(after["captureRevision"], before["captureRevision"] + 1)
            self.assertEqual(after["capture"]["stage"], "INCOMPLETE")
            self.assertEqual(after["capture"]["incompleteReason"], "SESSION_BOUNDARY_UNCERTAIN")
            self.assertEqual(after["capture"]["continuity"], "UNKNOWN")

    def recording_checkpoint(self, final_pending=False):
        self.boot(setup='function GetBattlefieldInstanceRunTime() return FixtureRuntime end; function GetBattlefieldStatus() return "active", "Darkspear Islands", FixtureInstanceId end')
        self.lua.execute('FixtureRuntime=60000; FixtureInstanceId=17')
        self.arm(); self.enter()
        self.lua.execute('FixtureScoreCount=2; fire("UPDATE_BATTLEFIELD_SCORE")')
        if final_pending:
            self.lua.execute('fire("PVP_MATCH_COMPLETE")')
        self.lua.execute('fire("PLAYER_LOGOUT")')
        return self.saved(), data(self.lua.globals().RBGSSettings)

    def resume_fixture(self, saved, settings, extra="", world=True):
        self.boot(saved, settings, setup='FixtureInstanceType="pvp"; FixtureNow=1791734410; FixtureRuntime=70000; FixtureInstanceId=17; function GetBattlefieldInstanceRunTime() return FixtureRuntime end; function GetBattlefieldStatus() return "active", "Darkspear Islands", FixtureInstanceId end; ' + extra)
        if world:
            self.lua.execute('fire("PLAYER_ENTERING_WORLD", false, true)')

    def test_reload_resumes_same_game_and_requires_fresh_scores(self):
        for final_pending in (False, True):
            with self.subTest(final_pending=final_pending):
                saved, settings = self.recording_checkpoint(final_pending)
                original = saved["captures"][0]
                self.resume_fixture(saved, settings, 'FixtureWinner=1; FixtureScoreCount=2')
                capture = self.last()["capture"]
                self.assertEqual(self.last()["captureId"], original["captureId"])
                self.assertEqual(capture["startedAt"], original["capture"]["startedAt"])
                self.assertEqual(capture["continuity"], "RESUMED")
                self.assertEqual(capture["interruptions"], [{"before": 1791734400, "after": 1791734410}])
                self.assertNotEqual(capture["stage"], "COMPLETE")
                self.assertIsNone(self.lua.globals().RBGSSettings.captureCheckpoint)
                self.lua.execute('tick(2)')
                self.assertNotEqual(self.last()["capture"]["stage"], "COMPLETE")
                self.lua.execute('fire("UPDATE_BATTLEFIELD_SCORE")')
                self.assertEqual(self.last()["capture"]["stage"], "COMPLETE")
                frozen = self.saved(); self.boot(frozen)
                self.assertEqual(self.saved(), frozen)

    def test_reload_rejects_other_game_character_client_and_stale_checkpoint(self):
        saved, settings = self.recording_checkpoint()
        for extra in ('FixtureInstanceId=18', 'FixtureRuntime=1000', 'FixtureRuntime=100000',
                      'FixtureNow=1791734600', 'FixtureNow=1791734390', 'FixtureInstanceType="none"',
                      'FixtureMapId=489', 'FixtureSurname="Other"', 'FixtureBuild="99999"',
                      'GetBattlefieldInstanceRunTime=nil'):
            with self.subTest(extra=extra):
                self.resume_fixture(saved, copy.deepcopy(settings), extra)
                self.assertEqual(self.last()["capture"]["stage"], "INCOMPLETE")
        stale = copy.deepcopy(settings); stale["captureCheckpoint"]["revision"] += 1
        self.resume_fixture(saved, stale)
        self.assertEqual(self.last()["capture"]["stage"], "INCOMPLETE")
        self.resume_fixture(saved, {})
        self.assertEqual(self.last()["capture"]["stage"], "INCOMPLETE")

    def test_login_and_missing_world_event_never_resume(self):
        saved, settings = self.recording_checkpoint()
        for event in ('fire("PLAYER_ENTERING_WORLD", true, false)', 'fire("PLAYER_ENTERING_WORLD")', 'tick(31)'):
            self.resume_fixture(saved, copy.deepcopy(settings), world=False)
            self.lua.execute(event)
            self.assertEqual(self.last()["capture"]["incompleteReason"], "SESSION_BOUNDARY_UNCERTAIN")

    def test_multiple_reloads_append_bounded_interruptions_and_preserve_roster(self):
        saved, settings = self.recording_checkpoint()
        self.resume_fixture(saved, settings)
        self.lua.execute('fire("PLAYER_LOGOUT")')
        saved, settings = self.saved(), data(self.lua.globals().RBGSSettings)
        self.resume_fixture(saved, settings, 'FixtureNow=1791734420; FixtureRuntime=80000')
        self.assertEqual(len(self.last()["capture"]["interruptions"]), 2)
        self.assertEqual(self.last()["capture"]["roster"], saved["captures"][0]["capture"]["roster"])
        self.lua.execute('FixtureWinner=1; FixtureScoreCount=2; fire("UPDATE_BATTLEFIELD_SCORE")')
        self.assertEqual(self.last()["capture"]["stage"], "COMPLETE")

    def test_prestart_and_frozen_final_clock_need_instance_identity(self):
        saved, settings = self.recording_checkpoint()
        settings["captureCheckpoint"]["runtimeMs"] = 0
        self.resume_fixture(saved, settings, 'FixtureRuntime=5000')
        self.assertEqual(self.last()["capture"]["continuity"], "RESUMED")
        settings["captureCheckpoint"]["instanceId"] = 0
        self.resume_fixture(saved, settings, 'FixtureRuntime=5000; FixtureInstanceId=0')
        self.assertEqual(self.last()["capture"]["stage"], "INCOMPLETE")
        saved, settings = self.recording_checkpoint(True)
        self.resume_fixture(saved, settings, 'FixtureRuntime=60000; FixtureWinner=1; FixtureScoreCount=2')
        self.lua.execute('fire("UPDATE_BATTLEFIELD_SCORE")')
        self.assertEqual(self.last()["capture"]["stage"], "COMPLETE")

    def test_anniversary_reload_keeps_wsg_provenance_and_finalizes(self):
        self.anniversary(); self.command("test-wsg " + TOKEN); self.enter()
        self.lua.execute('function GetBattlefieldInstanceRunTime() return 60000 end; fire("PLAYER_LOGOUT")')
        saved, settings = self.saved(), data(self.lua.globals().RBGSSettings)
        setup = '''WOW_PROJECT_BURNING_CRUSADE_CLASSIC=5; WOW_PROJECT_ID=5
            function GetBuildInfo() return "2.5.6", "70006", "fixture", 20506 end
            function UnitName() return "SyntheticHorde", "OtherRealm" end
            FixtureMapName="Warsong Gulch"; FixtureMapId=489; FixtureInstanceId=0'''
        self.resume_fixture(saved, settings, setup)
        self.assertEqual(self.last()["capture"]["continuity"], "RESUMED")
        self.finish()
        self.assertEqual(self.last()["capture"]["stage"], "COMPLETE")
        self.assertEqual(self.last()["client"], saved["captures"][0]["client"])
        self.assertEqual(self.last()["capture"]["map"]["gameMapId"], 489)

    def test_interruption_limit_and_malformed_gaps_preserve_data(self):
        saved, settings = self.recording_checkpoint()
        saved["captures"][0]["capture"].update(continuity="RESUMED", interruptions=[{"before":1791734400,"after":1791734400}] * 32)
        self.resume_fixture(saved, settings)
        self.assertEqual(self.last()["capture"]["stage"], "INCOMPLETE")
        self.assertEqual(len(self.last()["capture"]["interruptions"]), 32)
        for gaps in ([], [{"before":10,"after":9}], [{"before":10,"after":131}], [{"before":10,"after":20},{"before":15,"after":25}]):
            corrupt = copy.deepcopy(saved)
            corrupt["captures"][0]["capture"]["interruptions"] = gaps
            self.boot(corrupt)
            self.assertTrue(self.app.store.error)
            if not gaps:  # Empty Lua tables have no array/object distinction.
                corrupt["captures"][0]["capture"]["interruptions"] = {}
            self.assertEqual(self.saved(), corrupt)

    def test_reload_armed_and_terminal_keep_same_revision(self):
        self.arm(); snapshot = self.saved(); self.boot(snapshot)
        self.assertEqual(self.saved(), snapshot)
        self.enter(); self.finish(); snapshot = self.saved(); self.boot(snapshot)
        self.assertEqual(self.saved(), snapshot)

    def test_rearm_and_in_bg_arm_rejected(self):
        self.arm(); first = self.saved(); self.arm(TOKEN2)
        self.assertEqual(first, self.saved())
        self.enter(); self.finish(); terminal = self.saved(); self.arm(TOKEN2)
        self.assertEqual(terminal, self.saved())
        self.lua.execute('FixtureInstanceType="none"; fire("PLAYER_ENTERING_WORLD")')
        self.arm(); self.assertEqual(terminal, self.saved())

    def test_wrong_map_and_character_change_consume_attempt(self):
        self.arm(); self.lua.execute('FixtureMapId=489'); self.enter()
        self.assertEqual(self.last()["capture"]["incompleteReason"], "MAP_MISMATCH")
        self.boot(); self.arm(); self.lua.execute('FixtureCharacter="OtherCharacter"'); self.enter()
        self.assertEqual(self.last()["capture"]["incompleteReason"], "CHARACTER_CHANGED")
        self.assertEqual(self.last()["observedCharacter"]["name"], "SyntheticHorde FixtureSurname")

    def test_early_exit_and_final_timeout_preserve_capture(self):
        self.arm(); self.enter()
        self.lua.execute('FixtureInstanceType="none"; fire("PLAYER_ENTERING_WORLD")')
        self.assertEqual(self.last()["capture"]["incompleteReason"], "EARLY_EXIT")
        self.boot(); self.arm(); self.enter()
        self.lua.execute('fire("PVP_MATCH_COMPLETE"); tick(29)')
        self.assertEqual(self.last()["capture"]["stage"], "FINAL_PENDING")
        self.lua.execute('tick(2)')
        self.assertEqual(self.last()["capture"]["incompleteReason"], "MISSING_FINAL_OUTCOME")

    def test_cached_winner_at_entry_never_becomes_final(self):
        self.arm(); self.lua.execute('FixtureWinner=1; FixtureScoreCount=2'); self.enter()
        self.finish()
        self.assertEqual(self.last()["capture"]["state"], "INCOMPLETE")
        self.assertEqual(self.last()["capture"]["incompleteReason"], "SESSION_BOUNDARY_UNCERTAIN")

    def test_final_requires_fresh_notification_and_known_supported_winner(self):
        self.arm(); self.enter()
        self.lua.execute('FixtureScoreCount=2; fire("UPDATE_BATTLEFIELD_SCORE"); fire("PVP_MATCH_COMPLETE"); FixtureWinner=1; tick(2)')
        self.assertEqual(self.last()["capture"]["stage"], "FINAL_PENDING")
        self.lua.execute('FixtureWinner=2; fire("UPDATE_BATTLEFIELD_SCORE")')
        self.assertEqual(self.last()["capture"]["stage"], "FINAL_PENDING")
        self.lua.execute('FixtureWinner=0; fire("UPDATE_BATTLEFIELD_SCORE")')
        self.assertEqual(self.last()["capture"]["stage"], "COMPLETE")

    def test_unknown_score_fields_are_absent_not_zero(self):
        self.arm(); self.enter()
        self.lua.execute('function GetBattlefieldScore() return "Synthetic", nil, nil, 2, nil, 0, nil, nil, nil, nil, 0 end')
        self.finish()
        row = self.last()["capture"]["roster"][0]
        self.assertNotIn("killingBlows", row)
        self.assertNotIn("honorableKills", row)
        self.assertNotIn("damage", row)
        self.assertEqual(row["healing"], 0)

    def test_missing_optional_team_stays_unknown_instead_of_becoming_a_faction(self):
        self.arm(); self.enter()
        self.lua.execute('function GetBattlefieldScore() return "Synthetic", 1, 2, 3, nil, nil, nil, nil, nil, 100, 0 end')
        self.finish()
        self.assertEqual(self.last()["capture"]["stage"], "COMPLETE")
        self.assertNotIn("observedTeamKey", self.last()["capture"]["roster"][0])


    def test_unusable_or_oversized_roster_cannot_complete(self):
        self.arm(); self.enter()
        self.lua.execute('fire("PVP_MATCH_COMPLETE"); FixtureWinner=1; FixtureScoreCount=41; fire("UPDATE_BATTLEFIELD_SCORE")')
        self.assertEqual(self.last()["capture"]["stage"], "FINAL_PENDING")
        self.lua.execute('FixtureScoreCount=2; FixtureBadRow=true; fire("UPDATE_BATTLEFIELD_SCORE"); tick(31)')
        self.assertEqual(self.last()["capture"]["state"], "INCOMPLETE")

    def test_capacity_never_evicts_or_overwrites(self):
        for index in range(8):
            self.arm(TOKEN.replace("000000000003", f"{index+1:012d}")); self.command("cancel")
        snapshot = self.saved()
        self.arm(TOKEN.replace("000000000003", "000000000009"))
        self.assertEqual(self.saved(), snapshot)
        self.assertEqual(len(snapshot["captures"]), 8)

    def test_bounded_export_estimate_and_overflow_fail_closed(self):
        self.arm(); self.enter()
        self.lua.execute('fire("PVP_MATCH_COMPLETE"); FixtureScoreCount=40; FixtureWinner=1; fire("UPDATE_BATTLEFIELD_SCORE")')
        self.assertEqual(len(self.last()["capture"]["roster"]), 40)
        self.assertLess(self.app.Store.Size(self.lua.globals().RBGSMatchData.captures[1]), 200000)
        self.assertIsNone(self.lua.eval('function(size) return size({bad=string.rep("x", 513)}) end')(self.app.Store.Size))
        self.boot(); self.arm(); self.enter()
        self.lua.execute('function GetBattlefieldScore() return string.rep("x", 129), 0, 0, 0 end')
        self.finish(); self.lua.execute('tick(31)')
        self.assertEqual(self.last()["capture"]["state"], "INCOMPLETE")

    def test_store_overflow_preserves_previous_facts_and_reason(self):
        self.arm(); self.enter()
        previous = self.last()
        # Exercise the commit failure independently of adapter field filtering.
        self.lua.execute('''
            local record, index = RBGSMatchData.captures[1], 1
            FixtureCandidate = {captureId=record.captureId, captureRevision=record.captureRevision,
                assignmentCode=record.assignmentCode, client=record.client,
                observedCharacter=record.observedCharacter, capture={state="INCOMPLETE",
                stage="RECORDING", continuity="CONTINUOUS", incompleteReason="CAPTURE_PENDING",
                map=record.capture.map, startedAt=record.capture.startedAt,
                roster={{character={name=string.rep("x", 513)}}}, outcome={kind="UNKNOWN"}}}
        ''')
        self.app.store.Commit(self.app.store, 1, self.lua.globals().FixtureCandidate)
        after = self.last()
        self.assertEqual(after["capture"]["incompleteReason"], "STORAGE_FULL")
        self.assertEqual(after["capture"]["roster"], previous["capture"]["roster"])
        self.assertEqual(after["captureRevision"], previous["captureRevision"] + 1)

    def test_no_clock_or_map_label_never_creates_complete_capture(self):
        self.arm()
        self.lua.execute('GetServerTime=nil; time=nil')
        self.enter()
        self.assertEqual(self.last()["capture"]["incompleteReason"], "MISSING_REQUIRED_DATA")

    def test_roster_revisions_increase_only_when_content_changes(self):
        self.arm(); self.enter()
        self.lua.execute('FixtureScoreCount=2; fire("UPDATE_BATTLEFIELD_SCORE")')
        revision = self.last()["captureRevision"]
        self.lua.execute('fire("UPDATE_BATTLEFIELD_SCORE")')
        self.assertEqual(self.last()["captureRevision"], revision)
        self.lua.execute('function GetBattlefieldScore() return "Synthetic", 1, 2, 3, nil, 0 end; fire("UPDATE_BATTLEFIELD_SCORE")')
        self.assertEqual(self.last()["captureRevision"], revision + 1)

    def test_character_and_map_change_during_recording_fail_without_overwrite(self):
        self.arm(); self.enter()
        initial = self.last()
        self.lua.execute('FixtureCharacter="Changed"; tick(3)')
        self.assertEqual(self.last()["capture"]["incompleteReason"], "CHARACTER_CHANGED")
        self.assertEqual(self.last()["observedCharacter"], initial["observedCharacter"])
        self.boot(); self.arm(); self.enter()
        self.lua.execute('FixtureMapId=489; tick(3)')
        self.assertEqual(self.last()["capture"]["incompleteReason"], "MAP_MISMATCH")

    def test_arming_after_pvp_context_unknown_is_rejected(self):
        self.lua.execute('GetInstanceInfo=nil')
        self.arm()
        self.assertEqual(self.saved()["captures"], {})

    def test_store_rejects_cycles_invalid_utf8_and_sparse_arrays(self):
        self.assertIsNone(self.lua.eval('function(size) local a={}; a.self=a; return size(a) end')(self.app.Store.Size))
        self.assertFalse(self.lua.eval('function(check) return check(string.char(192, 128)) end')(self.app.Store.Text))
        self.assertFalse(self.lua.eval('function(check) return check(string.rep(string.char(195, 169), 129)) end')(self.app.Store.Text))
        self.lua.execute('FixtureInvalidRoot={schema=2,captures={[2]={}}}')
        blocked = self.app.Store.New(self.lua.globals().FixtureInvalidRoot)
        self.assertTrue(blocked.error)

    def test_serialized_lua_round_trip_and_size_reservation(self):
        self.arm(); self.enter()
        self.lua.execute('fire("PVP_MATCH_COMPLETE"); FixtureScoreCount=40; FixtureWinner=1; fire("UPDATE_BATTLEFIELD_SCORE")')
        # Synthetic WoW-style data serialization, not evaluation of a user file.
        self.lua.execute(r'''
            function serializeFixture(value, depth)
                depth = depth or 0
                if type(value) == "string" then return string.format("%q", value) end
                if type(value) == "number" then return tostring(value) end
                local out={"{\n"}
                for key, child in pairs(value) do
                    out[#out+1]=string.rep("\t", depth+1).."["..serializeFixture(key).."] = "
                        ..serializeFixture(child, depth+1)..",\n"
                end
                out[#out+1]=string.rep("\t", depth).."}"
                return table.concat(out)
            end
        ''')
        root = self.lua.globals().RBGSMatchData
        record = root.captures[1]
        serialized_record = self.lua.globals().serializeFixture(record)
        estimate = self.app.Store.Size(record)
        self.assertLess(len(serialized_record.encode("utf-8")), estimate)
        serialized_root = "RBGSMatchData = " + self.lua.globals().serializeFixture(root)
        snapshot = self.saved()
        restored = LuaRuntime(unpack_returned_tuples=True)
        restored.execute(serialized_root)
        self.boot(data(restored.globals().RBGSMatchData))
        self.assertEqual(self.saved(), snapshot)

    def test_terminal_reload_on_another_character_does_not_relabel_capture(self):
        self.arm(); self.enter(); self.finish()
        snapshot = self.saved()
        self.boot(snapshot)
        self.lua.execute('FixtureCharacter="OtherCharacter"; fire("PLAYER_LOGIN")')
        self.assertEqual(self.saved(), snapshot)

    def test_product_capture_works_with_debugger_enabled(self):
        ns = self.lua.table()
        for file in ("RBGSCompatibility.lua", "ProbePanel.lua"):
            self.lua.globals().loadAddon((ROOT / "RBGSCompatibility" / file).read_text(encoding="utf-8"), ns)
        self.lua.execute('fire("ADDON_LOADED", "RBGSCompatibility"); fire("PLAYER_LOGIN")')
        self.arm(); self.enter(); self.finish()
        self.assertEqual(self.last()["capture"]["stage"], "COMPLETE")
        self.assertTrue(self.lua.globals().RBGSCompatibilityData.records)

    def test_real_sanitized_final_restores_without_relabeling(self):
        fixture = json.loads((ROOT / "tools" / "fixtures" / "capture-70338-final.sanitized.json").read_text(encoding="utf-8"))
        self.boot(fixture)
        self.assertIsNone(self.app.store.error)
        self.assertEqual(self.saved(), fixture)
        capture = self.last()["capture"]
        self.assertEqual(capture["state"], "COMPLETE")
        self.assertEqual(capture["outcome"]["winningObservedTeamKey"], "1")
        self.assertEqual(len(capture["roster"]), 30)
        self.assertEqual(sum(row["observedTeamKey"] == "0" for row in capture["roster"]), 15)
        own = self.last()["observedCharacter"]["name"].casefold()
        self.assertFalse(any(row["character"]["name"].casefold() == own for row in capture["roster"]))
        self.lua.execute('FixtureCharacter="AnotherCharacter"; fire("PLAYER_LOGIN")')
        self.assertEqual(self.saved(), fixture)

    def test_completed_history_filters_orders_and_shows_detail_without_secrets(self):
        self.arm(); self.enter(); self.finish()
        self.command("history")
        self.assertTrue(self.lua.globals().RBGSProductPanel.shown)
        visible = self.lua.globals().visibleText()
        self.assertIn("Alliance won", visible)
        self.assertIn("FINAL SCOREBOARD", visible)
        self.assertNotIn("0123456789ABCDEF", visible)
        self.lua.execute('FixtureInstanceType="none"; fire("PLAYER_ENTERING_WORLD"); FixtureWinner=nil')
        self.arm(TOKEN2)
        self.assertEqual(len(self.app.CompletedMatches()), 1)
        self.enter(); self.finish(0)
        self.command("history")
        self.assertEqual(len(self.app.CompletedMatches()), 2)
        self.assertIn("2 players", self.lua.globals().visibleText())
        self.lua.execute('click(RBGSHistoryNext)')
        self.assertIn("COMPLETED MATCH 2 / 2", self.lua.globals().visibleText())
        self.lua.execute('click(RBGSProductHistory)')
        self.assertIn("Saved recordings: 2 / 8", self.lua.globals().visibleText())

    def test_corrupt_or_unknown_saved_data_is_preserved_and_blocks_arming(self):
        for saved in ({"schema": 99, "captures": []}, {"schema": 2, "captures": [{"broken": "retained"}]}):
            self.boot(saved); self.arm()
            self.assertTrue(self.app.store.error)
            expected = data(self.lua.globals().RBGSMatchData)
            self.command("cancel"); self.command("clear"); self.assertEqual(self.saved(), expected)

    def test_new_build_version_and_interface_are_metadata_not_capture_gates(self):
        for version, build, interface in (("1.60.2", "99999", 16002), ("1.61.0", "100001", 16100)):
            with self.subTest(build=build):
                self.boot()
                self.lua.execute(f'function GetBuildInfo() return "{version}", "{build}", "fixture", {interface} end; fire("PLAYER_LOGIN")')
                self.arm(); self.enter(); self.finish()
                self.assertEqual(self.last()["capture"]["stage"], "COMPLETE")
                self.assertEqual(self.last()["client"]["gameVersion"], version)
                self.assertEqual(self.last()["client"]["gameBuild"], build)
                self.assertEqual(self.last()["client"]["interface"], interface)
                self.assertEqual(self.last()["client"]["adapterVersion"], "darkspear-scoreboard-v1")


    def test_missing_identity_cannot_arm(self):
        self.lua.execute('function UnitName() return nil end'); self.arm()
        self.assertEqual(self.saved()["captures"], {})


    def classic_scoreboard(self):
        self.lua.execute('''WorldStateScoreFrame=CreateFrame("Frame", "WorldStateScoreFrame", UIParent)
            WorldStateScoreFrameLeaveButton=CreateFrame("Button", "WorldStateScoreFrameLeaveButton", WorldStateScoreFrame)
            WorldStateScoreFrameLeaveButton:SetSize(153,21)
            WorldStateScoreFrameLeaveButton:SetScript("OnClick",function() FixtureLeft=true end)
            WorldStateScoreFrame:SetScript("OnShow",function() WorldStateScoreFrameLeaveButton:Show() end)''')

    def test_anniversary_scoreboard_saves_reloads_and_reopens_classic_exit_once(self):
        self.anniversary(); self.command("test-wsg " + TOKEN); self.enter(); self.classic_scoreboard()
        self.lua.execute('FixtureWinner=0; fire("PVP_MATCH_COMPLETE"); tick(0.5)')
        button = self.lua.globals().RBGSScoreboardSaveResults
        self.assertTrue(button.shown)
        self.assertFalse(button.enabled)
        self.assertFalse(self.lua.globals().WorldStateScoreFrameLeaveButton.shown)
        self.lua.execute('FixtureScoreCount=2; fire("UPDATE_BATTLEFIELD_SCORE"); tick(0.5)')
        self.assertTrue(button.enabled)
        self.assertEqual(button.text, "rbgs.io: Save results")
        self.assertEqual(button.point[1], "CENTER")
        self.lua.execute('WorldStateScoreFrameLeaveButton:Show()')
        self.assertFalse(self.lua.globals().WorldStateScoreFrameLeaveButton.shown)
        saved = self.saved()
        self.lua.execute('click(RBGSScoreboardSaveResults)')
        self.assertTrue(self.lua.globals().FixtureReloaded)
        self.assertFalse(bool(self.lua.globals().FixtureLeft))
        self.assertEqual(self.saved(), saved)
        settings = data(self.lua.globals().RBGSSettings)
        self.assertEqual(settings["reopenResults"]["captureId"], self.last()["captureId"])
        self.boot(saved, settings); self.anniversary(); self.classic_scoreboard()
        self.lua.execute('''WorldStateScoreFrame:Hide(); FixtureInstanceType="pvp"; FixtureWinner=0; FixtureScoreCount=2
            function LeaveBattlefield() error("never leave automatically") end
            fire("PLAYER_ENTERING_WORLD",false,true); tick(0.5)''')
        self.assertTrue(self.lua.globals().WorldStateScoreFrame.shown)
        self.assertTrue(self.lua.globals().WorldStateScoreFrameLeaveButton.shown)
        self.assertIsNone(self.lua.globals().RBGSScoreboardSaveResults)
        self.assertIsNone(self.lua.globals().RBGSSettings.reopenResults)
        self.assertEqual(self.saved(), saved)
        self.lua.execute('WorldStateScoreFrame:Hide(); tick(2)')
        self.assertFalse(self.lua.globals().WorldStateScoreFrame.shown)
        self.lua.execute('WorldStateScoreFrame:Show(); click(WorldStateScoreFrameLeaveButton)')
        self.assertTrue(self.lua.globals().FixtureLeft)

    def test_anniversary_scoreboard_leaves_native_exit_for_unassigned_wrong_map_and_combat(self):
        self.anniversary(); self.classic_scoreboard(); self.lua.execute('tick(0.5)')
        self.assertTrue(self.lua.globals().WorldStateScoreFrameLeaveButton.shown)
        self.assertIsNone(self.lua.globals().RBGSScoreboardSaveResults)
        self.command("test-wsg " + TOKEN); self.enter(); self.finish()
        self.lua.execute('FixtureCombat=true; tick(0.5)')
        self.assertTrue(self.lua.globals().WorldStateScoreFrameLeaveButton.shown)
        self.lua.execute('FixtureCombat=false; tick(0.5)')
        self.assertTrue(self.lua.globals().RBGSScoreboardSaveResults.enabled)
        self.lua.execute('FixtureCombat=true; click(RBGSScoreboardSaveResults)')
        self.assertFalse(bool(self.lua.globals().FixtureReloaded))
        self.lua.execute('FixtureCombat=false; FixtureMapId=529; fire("PLAYER_ENTERING_WORLD"); tick(0.5)')
        self.assertTrue(self.lua.globals().WorldStateScoreFrameLeaveButton.shown)
        self.assertFalse(self.lua.globals().RBGSScoreboardSaveResults.shown)

    def anniversary(self):
        self.lua.execute('''WOW_PROJECT_BURNING_CRUSADE_CLASSIC=5; WOW_PROJECT_ID=5
            function GetBuildInfo() return "2.5.6", "70006", "fixture", 20506 end
            function UnitName() return "SyntheticHorde", "OtherRealm" end
            function GetBattlefieldScore(index)
                return index == 1 and "SyntheticHorde-Fixture Realm" or "SyntheticAlliance-Other Realm",
                    8, 63, 2, 100, index == 1 and 0 or 1, 0, "Blood Elf", "Paladin", "PALADIN", 31097, 384
            end
            FixtureMapName="Warsong Gulch"; FixtureMapId=489; fire("PLAYER_LOGIN")''')

    def test_anniversary_requires_explicit_test_command_and_preserves_actual_identity(self):
        self.anniversary()
        self.arm()
        self.assertEqual(self.saved()["captures"], {})
        self.command("test-wsg " + TOKEN)
        self.assertEqual(self.last()["observedCharacter"]["name"], "SyntheticHorde")
        self.assertNotIn("OtherRealm", self.last()["observedCharacter"]["name"])
        self.enter(); self.finish()
        record = self.last()
        self.assertEqual(record["capture"]["stage"], "COMPLETE")
        self.assertEqual(record["capture"]["map"]["profile"], "TBC_ANNIVERSARY_WSG_TEST")
        self.assertEqual(record["client"]["product"], "wow_anniversary")
        self.assertEqual(record["client"]["gameBuild"], "70006")
        self.assertEqual(record["capture"]["roster"][0]["character"]["name"], "SyntheticHorde")
        self.assertEqual(record["capture"]["roster"][0]["damage"], 31097)
        self.assertEqual(record["capture"]["roster"][0]["healing"], 384)
        saved = self.saved(); self.boot(saved); self.anniversary()
        self.assertEqual(self.saved(), saved)

    def test_wsg_flag_columns_are_persisted_with_zero_and_sorted_player_indices(self):
        self.anniversary(); self.command("test-wsg " + TOKEN); self.enter()
        self.lua.execute('''function GetNumBattlefieldStats() return 2 end
            function GetBattlefieldStatData(player, column)
                if column==1 then return player-1 else return player+2 end
            end''')
        self.finish()
        rows = self.last()["capture"]["roster"]
        self.assertEqual([(r["flagsCaptured"],r["flagsReturned"]) for r in rows], [(0,3),(1,4)])
        self.assertIn("Flags captured: 0", self.app.HistoryText(1))
        saved = self.saved(); self.boot(saved); self.anniversary()
        self.assertEqual(self.saved(), saved)

    def test_flag_apis_are_optional_and_bad_values_stay_unknown(self):
        for script in ('', 'function GetNumBattlefieldStats() error("unavailable") end',
                       'function GetNumBattlefieldStats() return 1 end; function GetBattlefieldStatData() return 1 end',
                       'function GetNumBattlefieldStats() return 3 end; function GetBattlefieldStatData() return 1 end',
                       'function GetNumBattlefieldStats() return 2 end; function GetBattlefieldStatData() error("unavailable") end',
                       'function GetNumBattlefieldStats() return 2 end; function GetBattlefieldStatData(_,c) if c==1 then return -1 else return "2" end end'):
            with self.subTest(script=script):
                self.boot(); self.anniversary(); self.command("test-wsg " + TOKEN); self.enter()
                self.lua.execute(script); self.finish()
                self.assertEqual(self.last()["capture"]["stage"], "COMPLETE")
                for row in self.last()["capture"]["roster"]:
                    self.assertNotIn("flagsCaptured",row); self.assertNotIn("flagsReturned",row)
        self.boot(); self.anniversary(); self.command("test-wsg " + TOKEN); self.enter()
        self.lua.execute('function GetNumBattlefieldStats() return 2 end; function GetBattlefieldStatData(_,c) if c==2 then return 0 end end')
        self.finish(); row=self.last()["capture"]["roster"][0]
        self.assertNotIn("flagsCaptured", row); self.assertEqual(row["flagsReturned"],0)

    def test_other_battleground_objectives_are_never_labeled_as_flags(self):
        self.arm(); self.enter()
        self.lua.execute('function GetNumBattlefieldStats() return 2 end; function GetBattlefieldStatData() error("must not read Darkspear objectives") end')
        self.finish()
        row = self.last()["capture"]["roster"][0]
        self.assertNotIn("flagsCaptured", row); self.assertNotIn("flagsReturned", row)

    def test_anniversary_wrong_map_and_uncertain_reload_preserve_incomplete_attempts(self):
        self.anniversary(); self.command("test-wsg " + TOKEN)
        self.lua.execute('FixtureMapId=529')
        self.enter()
        self.assertEqual(self.last()["capture"]["incompleteReason"], "MAP_MISMATCH")
        self.boot(); self.anniversary(); self.command("test-wsg " + TOKEN); self.enter()
        saved = self.saved(); self.boot(saved)
        self.assertEqual(self.last()["capture"]["state"], "INCOMPLETE")
        self.assertEqual(self.last()["client"]["product"], "wow_anniversary")

    def test_anniversary_class_token_is_not_a_stat_and_optional_numbers_keep_their_meaning(self):
        self.anniversary(); self.command("test-wsg " + TOKEN); self.enter()
        # The reported real TBC tuple has 3/55/8 at 2/3/4, PALADIN at 10,
        # and 39820 at 11. Healing below is synthetic, not inferred from damage.
        self.lua.execute('''function GetBattlefieldScore()
            return "Synthetic-Fixture Realm",3,55,8,100,0,0,"Blood Elf","Paladin","PALADIN",39820,nil
        end''')
        self.finish()
        row = self.last()["capture"]["roster"][0]
        self.assertEqual(self.last()["capture"]["stage"], "COMPLETE")
        self.assertEqual([row["killingBlows"],row["honorableKills"],row["deaths"],row["damage"]], [3,55,8,39820])
        self.assertNotIn("healing", row)
        for damage, healing in (("0", "0"), ("nil", "384")):
            self.boot(); self.anniversary(); self.command("test-wsg " + TOKEN); self.enter()
            self.lua.execute('function GetBattlefieldScore() return "Synthetic",3,55,8,100,0,0,"Blood Elf","Paladin","PALADIN",' + damage + ',' + healing + ' end')
            self.finish()
            row = self.last()["capture"]["roster"][0]
            self.assertEqual(self.last()["capture"]["stage"], "COMPLETE")
            self.assertEqual(row.get("damage"), None if damage == "nil" else 0)
            self.assertEqual(row["healing"], int(healing))

    def test_anniversary_rejects_bad_stats_at_its_own_positions(self):
        for damage, healing in (('"shifted"', "0"), ("0", '"shifted"'), ("-1", "0")):
            self.boot(); self.anniversary(); self.command("test-wsg " + TOKEN); self.enter()
            self.lua.execute('function GetBattlefieldScore() return "Synthetic",3,55,8,100,0,0,"Blood Elf","Paladin","PALADIN",' + damage + ',' + healing + ' end')
            self.finish()
            self.assertEqual(self.last()["capture"]["stage"], "FINAL_PENDING")
            self.assertIn("statistics", self.app.Adapter.Problem())
            self.lua.execute('tick(31)')
            self.assertEqual(self.last()["capture"]["stage"], "INCOMPLETE")

    def test_forever_rejects_temporary_test_command(self):
        self.command("test-wsg " + TOKEN)
        self.assertEqual(self.saved()["captures"], {})

    def test_missing_required_api_prevents_arming_with_specific_reason(self):
        for name in ("GetBattlefieldScore", "GetBattlefieldWinner", "RequestBattlefieldScoreData"):
            with self.subTest(api=name):
                self.boot()
                self.lua.execute(f'{name}=nil; fire("PLAYER_LOGIN")')
                self.arm()
                self.assertEqual(self.saved()["captures"], {})
                self.assertIn(name, self.app.adapterError)


    def test_malformed_version_metadata_cannot_arm(self):
        for version, build, interface in (("1..60", "99999", 16002), ("1.60.2", "bad", 16002),
                                           ("1.60.2", "00000", 16002), ("1.60.2", "99999", 0)):
            with self.subTest(metadata=(version, build, interface)):
                self.boot()
                self.lua.execute(f'function GetBuildInfo() return "{version}", "{build}", "fixture", {interface} end; fire("PLAYER_LOGIN")')
                self.arm()
                self.assertEqual(self.saved()["captures"], {})
                self.assertIn("game version", self.app.adapterError)


    def test_changed_scoreboard_shapes_never_become_completed_captures(self):
        for expression in ('"Synthetic", 1, 2, 3',
                           '"Synthetic", 1, 2, 3, 0, 0, nil, nil, nil, "shifted", 0',
                           '"Synthetic", 1, 2, 3, 0, 7, nil, nil, nil, 100, 0'):
            with self.subTest(scoreboard=expression):
                self.boot(); self.arm(); self.enter()
                self.lua.execute('function GetBattlefieldScore() return ' + expression + ' end')
                self.finish()
                self.assertEqual(self.last()["capture"]["stage"], "FINAL_PENDING")
                self.assertIn("scoreboard", self.app.Adapter.Problem())
                self.lua.execute('tick(31)')
                self.assertEqual(self.last()["capture"]["state"], "INCOMPLETE")


    def test_build_change_does_not_rewrite_already_saved_captures(self):
        self.arm(); self.enter(); self.finish()
        before = self.saved()
        self.boot(before)
        self.lua.execute('function GetBuildInfo() return "1.61.0", "100001", "fixture", 16100 end; fire("PLAYER_LOGIN")')
        self.assertEqual(self.saved(), before)


    def test_patch_during_armed_attempt_preserves_provenance_and_allows_a_fresh_attempt(self):
        self.arm()
        previous_client = self.last()["client"]
        self.lua.execute('function GetBuildInfo() return "1.61.0", "100001", "fixture", 16100 end; fire("PLAYER_LOGIN")')
        self.assertEqual(self.last()["client"], previous_client)
        self.assertEqual(self.last()["capture"]["incompleteReason"], "SESSION_BOUNDARY_UNCERTAIN")
        self.arm(TOKEN2); self.enter(); self.finish()
        self.assertEqual(self.last()["client"]["gameBuild"], "100001")
        self.assertEqual(self.last()["capture"]["state"], "COMPLETE")

    def test_product_panel_launcher_and_reload_guard(self):
        self.command("show")
        self.assertTrue(self.lua.globals().RBGSProductPanel.shown)
        self.lua.execute('click(RBGSProductLauncher)')
        self.assertFalse(self.lua.globals().RBGSProductPanel.shown)
        self.arm(); self.enter(); self.command("reload")
        self.assertIsNone(self.lua.globals().FixtureReloaded)
        self.finish(); self.lua.execute('FixtureCombat=true'); self.command("reload")
        self.assertIsNone(self.lua.globals().FixtureReloaded)

    def test_debugger_clear_does_not_touch_product_captures(self):
        self.arm(); self.enter(); self.finish(); snapshot = self.saved()
        ns = self.lua.table()
        for file in ("RBGSCompatibility.lua", "ProbePanel.lua"):
            self.lua.globals().loadAddon((ROOT / "RBGSCompatibility" / file).read_text(encoding="utf-8"), ns)
        self.lua.execute('fire("ADDON_LOADED", "RBGSCompatibility"); fire("PLAYER_LOGIN"); click(RBGSProbeClear)')
        self.assertEqual(self.saved(), snapshot)

    def test_export_matches_optional_local_contract(self):
        schema_path = os.environ.get("RBGS_CAPTURE_SCHEMA_PATH")
        if not schema_path:
            self.skipTest("Set RBGS_CAPTURE_SCHEMA_PATH to validate against the private contract")
        import jsonschema
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
        self.arm(); validator.validate(json_envelope(self.saved()))
        self.enter(); validator.validate(json_envelope(self.saved()))
        self.finish(); validator.validate(json_envelope(self.saved()))
        self.boot(); self.arm(); self.enter(); self.lua.execute('FixtureInstanceType="none"; fire("PLAYER_ENTERING_WORLD")')
        validator.validate(json_envelope(self.saved()))
        self.boot(); self.arm(); self.command("cancel")
        validator.validate(json_envelope(self.saved()))
        fixture = json.loads((ROOT / "tools" / "fixtures" / "capture-70338-final.sanitized.json").read_text(encoding="utf-8"))
        validator.validate(json_envelope(fixture))
        saved, settings = self.recording_checkpoint()
        self.resume_fixture(saved, settings)
        validator.validate(json_envelope(self.saved()))
        self.finish(); validator.validate(json_envelope(self.saved()))
        self.boot(); self.anniversary(); self.command("test-wsg " + TOKEN)
        validator.validate(json_envelope(self.saved()))
        self.lua.execute('function GetNumBattlefieldStats() return 2 end; function GetBattlefieldStatData(_,column) return column-1 end')
        self.enter(); self.finish(); validator.validate(json_envelope(self.saved()))


if __name__ == "__main__":
    unittest.main()
