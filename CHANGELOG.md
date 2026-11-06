# Changelog

## 0.2.2-alpha.1 — Forever WSG capture tests

- Adds an explicit Forever WSG test command issued by the updated companion: `/rbgs test-forever-wsg RB2:<captureId>:<assignmentCode>`.
- Records the final WSG scoreboard, including per-player flag captures and returns when readable and matched to the same player.
- Keeps WSG tests separate from historical Darkspear and TBC captures. Missing optional values stay unknown.
- Supports Save results/reload/reopen and the existing conservative same-game reload recovery.
- Requires the updated web/API and companion. Moderator can select an owned Forever character at its current level for an individual capture-only test.

Local checks replay the anonymized real WSG scoreboard and validate the delivery/receipt flow. A new live product test is still required. These tests do not affect ratings or enable ranked matchmaking.

## 0.2.1-alpha.1 — Forever

- The player addon now installs into `Interface/AddOns/rbgs.io`, with matching TOC and texture paths.
- Keeps the existing Forever Darkspear capture, completed history and guarded Save results/reload flow.
- SavedVariables now use the filename `rbgs.io.lua`. Old `RBGS.lua` captures are not automatically migrated. Remove the old `RBGS` addon folder when switching, then fully restart WoW.
- Requires an updated companion that recognizes the renamed addon and data file.

This is an alpha of the existing Forever addon. Live WSG observations and per-player flags have been validated in the separate developer probe; they are not yet enabled as a WSG capture/upload profile in this player addon. This package does not include the probe, enable matchmaking or establish ranked results.
