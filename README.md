# addon.rbgs.io

WoW: Forever addons for rbgs.io. `RBGSCompatibility/` is displayed in-game as **rbgs.io Debugger** and targets interface 16001. It records bounded diagnostic observations; it does not verify matches or upload data.

## Local installation

Copy `RBGSCompatibility/` into `<World of Warcraft>/_classic_beta_/Interface/AddOns/`, restart WoW and enable **rbgs.io Debugger**. The red minimap button opens the panel; left-click toggles it and drag repositions it. `/rbgsprobe` also opens the panel. Per-character `RBGSDebuggerSettings` stores the minimap position.

The panel supports manual capture, capability inspection and automatic BG entry/final-result observation. Account-level `RBGSCompatibilityData` is saved to `WTF/Account/<account>/SavedVariables/RBGSCompatibility.lua` on `/reload` or logout. Use the companion's selected-account diagnostic reader to inspect persisted data. SavedVariables do not update continuously.

**Clear history** clears diagnostic records and requires an out-of-combat reload. The panel preserves history when reload is unavailable or fails. Capture history is bounded to 300 records; unavailable statistics remain unknown.

The red debugger logo is a 256×256 RGBA TGA texture in `RBGSCompatibility/Media/`; its PNG source is in `branding/`. The internal addon name and SavedVariables root remain compatible with previous diagnostic captures.

## Verification

Requires Python and the Lua 5.1 test runtime, only for development:

```powershell
python -m pip install -r tools/requirements-test.txt
python -m unittest discover -s tools -p test_probe_panel.py
```

Tests use synthetic WoW APIs. The optional companion-parser integration requires a sibling `companion.rbgs.io` checkout; it is skipped when unavailable. Actual Forever rendering and game API behavior require local acceptance checks.

## Product addon

Copy `RBGS/` into the beta client's `Interface/AddOns/`, restart WoW and enable **rbgs.io**. The debugger can remain enabled. The product uses the original logo and separate per-character `RBGSSettings` for its minimap button.

The controlled `darkspear-scoreboard-v1` adapter captures Darkspear Islands (`2997`). It checks required game functions and bounded name, map, result and scoreboard data instead of rejecting a new build number. Actual game version, build and interface are saved with each capture. Missing optional statistics remain unknown; unreadable required data cannot produce a completed capture. WoW's own addon-loading Interface metadata may still need updating after an interface change. Before entering the BG, paste the assignment command issued by the companion:

```text
/rbgs match RB2:<captureId>:<assignmentCode>
```

The capture ID is a UUID; the assignment code is 16 uppercase Crockford-base32 characters. The addon observes the next supported BG and never imports a previous scoreboard. `/rbgs status` displays attempts; `/rbgs cancel` terminates and retains the active attempt. Codes are excluded from status/chat output.

After the final result, remain in the BG until status is `COMPLETE`, then use `/reload` or **Save / reload**. Reloading during capture preserves an `INCOMPLETE / SESSION_BOUNDARY_UNCERTAIN` attempt. The save button guards active capture; no reload happens automatically. Wrong map, changed character, early exit and unavailable final results retain incomplete attempts.

**Completed matches** or `/rbgs history` displays completed captures newest first. **Newer/Older** navigates map, UTC times, winning faction, roster and observed statistics. Unknown values stay unknown. Completed snapshots are frozen under their own ID/revision; history does not verify or erase them.

WoW persists account-level `RBGSMatchData` to `WTF/Account/<account>/SavedVariables/RBGS.lua` on reload/logout. Product schema 2 is separate from diagnostic data; debugger **Clear history** cannot erase product captures. Storage holds eight attempts, at most 40 roster rows and a conservative 200,000-byte Lua estimate per attempt. Capacity exhaustion refuses new data without evicting previous captures. There is no product erase button or automatic pruning.

The companion reads this separate product file and preserves observed revisions in its durable inbox. Assigned terminal captures are uploaded by the companion, not by the addon. Controlled reports go to review; no verified result, ownership or rating is established by capture alone.

```powershell
python -m unittest discover -s tools -p test_product_capture.py
```

Product tests cover successive games, frozen revisions, reloads, wrong map/character, stale scoreboards, persistence, capacity, history and debugger isolation. Optional contract validation uses `RBGS_CAPTURE_SCHEMA_PATH` with `jsonschema` installed; local specifications are not part of this repository.
