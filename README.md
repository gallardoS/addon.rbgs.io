# addon.rbgs.io

Automatic Forever publication: main builds publish Alphas and version tags publish stable Releases. See [RELEASING.md](RELEASING.md) for the GitHub Action, versioning, ZIP contents and one-time `CF_API_KEY` secret setup.

Product directory rename (2026-11-05): install `rbgs.io/`, with `rbgs.io.toc` for Forever and `rbgs.io_TBC.toc` for the temporary TBC tests. WoW now saves product data to `SavedVariables/rbgs.io.lua`. Lua globals `RBGSMatchData`/`RBGSSettings`, `/rbgs`, and the schema stay unchanged. Remove the previous `RBGS/` installation when switching so both addons cannot load together, then fully restart WoW. Existing `RBGS.lua` data is not automatically migrated; this installation intentionally starts fresh. The updated companion supports both layouts and uses only `rbgs.io.lua` when the new addon folder is present.

Players install only `rbgs.io/`, displayed in WoW as **rbgs.io**. It records assigned match data for the companion. `RBGSCompatibility/`, displayed as **rbgs.io Debugger**, is an optional developer tool for investigating game APIs and compatibility. It is not required by players or by the companion's normal match workflow.

## Optional developer debugger installation

Copy `RBGSCompatibility/` into `<World of Warcraft>/_classic_beta_/Interface/AddOns/`, restart WoW and enable **rbgs.io Debugger**. The red minimap button opens the panel; left-click toggles it and drag repositions it. `/rbgsprobe` also opens the panel. Per-character `RBGSDebuggerSettings` stores the minimap position.

The panel supports manual capture, capability inspection and automatic BG entry/final-result observation. Account-level `RBGSCompatibilityData` is saved to `WTF/Account/<account>/SavedVariables/RBGSCompatibility.lua` on `/reload` or logout. Use the companion's selected-account diagnostic reader to inspect persisted data. SavedVariables do not update continuously.

**Clear history** clears diagnostic records and requires an out-of-combat reload. The panel preserves history when reload is unavailable or fails. Capture history is bounded to 300 records; unavailable statistics remain unknown.

The red debugger logo is a 256x256 RGBA TGA texture in `RBGSCompatibility/Media/`; its PNG source is in `branding/`. The internal addon name and SavedVariables root remain compatible with previous diagnostic captures.

## Verification

Requires Python and the Lua 5.1 test runtime, only for development:

```powershell
python -m pip install -r tools/requirements-test.txt
python -m unittest discover -s tools -p test_probe_panel.py
```

Tests use synthetic WoW APIs. The optional companion-parser integration requires a sibling `companion.rbgs.io` checkout; it is skipped when unavailable. Actual Forever rendering and game API behavior require local acceptance checks.

## Product addon

Copy `rbgs.io/` into the beta client's `Interface/AddOns/`, restart WoW and enable **rbgs.io**. Developers may keep the separate debugger enabled; players do not need it. The product uses the original logo and separate per-character `RBGSSettings` for its minimap button.

The controlled `darkspear-scoreboard-v1` adapter captures Darkspear Islands (`2997`). It checks required game functions and bounded name, map, result and scoreboard data instead of rejecting a new build number. Actual game version, build and interface are saved with each capture. Missing optional statistics remain unknown; unreadable required data cannot produce a completed capture. Temporary TBC Anniversary WSG tests also record per-player flags captured and returned from the battleground objective columns when available; missing or unreadable objectives stay unknown. Historical captures are not backfilled. WoW's own addon-loading Interface metadata may still need updating after an interface change. Before entering the BG, paste the assignment command issued by the companion:

```text
/rbgs match RB2:<captureId>:<assignmentCode>
```

The capture ID is a UUID; the assignment code is 16 uppercase Crockford-base32 characters. The addon observes the next supported BG and never imports a previous scoreboard. `/rbgs status` displays attempts; `/rbgs cancel` terminates and retains the active attempt. Codes are excluded from status/chat output.

After the final result, remain in the BG until the recording is complete. During an assigned recording, **rbgs.io: Save results** temporarily replaces the scoreboard Leave match button in the same position. Click it when enabled. It uses the native WoW button style, waits for the final recording and refuses to reload in combat. Its tooltip explains that reloading saves the data for the companion to upload. After this reload, the addon reopens the final scoreboard once with the original **Leave match** button available. Leaving still requires your click. The same save/reload/reopen flow applies to the explicit TBC Anniversary WSG test, using the Classic scoreboard and its original exit button. The short-lived reopen request belongs to the completed capture and is consumed on load; it does not reopen on normal login or another game. Capture/reload/UI failures restore the native exit. Unassigned battlegrounds keep their normal exit. This does not report an upload receipt. If the scoreboard is unavailable, use `/reload`, **Save / reload** in the addon panel, or log out. A mid-match `/reload` can resume the same capture when character, client, map and the battleground clock match a fresh saved checkpoint. Reload gaps are retained as `RESUMED` continuity with interruption timestamps; the final scoreboard still requires a fresh update. A normal login, missing or inconsistent checkpoint, a reload longer than 120 seconds, or more than 32 interruptions ends the attempt as `INCOMPLETE / SESSION_BOUNDARY_UNCERTAIN`. Old terminal attempts stay frozen. The save button guards active capture; no reload happens automatically. Wrong map, changed character, early exit and unavailable final results retain incomplete attempts.

**Completed matches** or `/rbgs history` displays completed captures newest first. **Newer/Older** navigates map, UTC times, winning faction, roster and observed statistics. Unknown values stay unknown. Completed snapshots are frozen under their own ID/revision; history does not verify or erase them.

WoW persists account-level `RBGSMatchData` to `WTF/Account/<account>/SavedVariables/rbgs.io.lua` on reload/logout. Product schema 2 is separate from diagnostic data; debugger **Clear history** cannot erase product captures. Storage holds eight attempts, at most 40 roster rows and a conservative 200,000-byte Lua estimate per attempt. Capacity exhaustion refuses new data without evicting previous captures. There is no product erase button or automatic pruning.

The companion reads this separate product file and preserves observed revisions in its durable inbox. Assigned terminal captures are uploaded by the companion, not by the addon. Controlled reports go to review; no verified result, ownership or rating is established by capture alone.

```powershell
python -m unittest discover -s tools -p test_product_capture.py
```

Product tests cover successive games, frozen revisions, reloads, wrong map/character, stale scoreboards, persistence, capacity, history and debugger isolation. Optional contract validation uses `RBGS_CAPTURE_SCHEMA_PATH` with `jsonschema` installed; local specifications are not part of this repository.
