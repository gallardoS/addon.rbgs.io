# Changelog

## 0.2.1-alpha.1 — Forever

- The player addon now installs into `Interface/AddOns/rbgs.io`, with matching TOC and texture paths.
- Keeps the existing Forever Darkspear capture, completed history and guarded Save results/reload flow.
- SavedVariables now use the filename `rbgs.io.lua`. Old `RBGS.lua` captures are not automatically migrated. Remove the old `RBGS` addon folder when switching, then fully restart WoW.
- Requires an updated companion that recognizes the renamed addon and data file.

This is an alpha of the existing Forever addon. Live WSG observations and per-player flags have been validated in the separate developer probe; they are not yet enabled as a WSG capture/upload profile in this player addon. This package does not include the probe, enable matchmaking or establish ranked results.
