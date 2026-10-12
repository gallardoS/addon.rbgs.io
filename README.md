# addon.rbgs.io

WoW: Forever diagnostic addon for rbgs.io. `RBGSCompatibility/` is displayed in-game as **rbgs.io Debugger** and targets interface 16001. It records bounded diagnostic observations; it does not verify matches or upload data.

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
