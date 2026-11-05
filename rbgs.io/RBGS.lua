local addonName, app = ...
local Store, Adapter = app.Store, app.Adapter
local frame = CreateFrame("Frame", "RBGSCaptureEvents")
local loaded, loggedIn, context, cleanEntry, freshScores = false, false, nil, false, false
local pollElapsed, finalElapsed = 0, 0
local currentCaptureId
local restorePending, reloadCheckpoint, restoreElapsed = false, nil, 0

function app.Message(message)
    if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage("rbgs.io: " .. message) end
end
local function refresh()
    if app.Refresh then app.Refresh() end
    if app.RefreshResultsButton then pcall(app.RefreshResultsButton) end
end
local function changed(oldStage)
    local active = app.store and app.store:Active()
    if oldStage and not active then
        app.Message("Recording ended. Use /reload before leaving to save your match data. Check /rbgs status for details.")
    end
    refresh()
end
local function updateContext()
    if not loggedIn or not app.store or app.store.error then return end
    if restorePending then return end
    local inBG, map = Adapter.Context()
    if inBG == nil then return end
    local wasBG = context
    context = inBG
    if inBG ~= true or wasBG ~= true then currentCaptureId = nil end
    local record = app.store:Active()
    if not record then return end
    local stage = record.capture.stage
    if inBG then
        if stage == "ARMED" then
            local winner, readable = Adapter.Winner()
            cleanEntry = wasBG == false and readable and winner == nil
            freshScores, finalElapsed = false, 0
            app.store:Enter(Adapter.Identity(), map, Adapter.Time(), cleanEntry)
            local entered = app.store:Active()
            if entered and entered.capture.stage == "RECORDING" then currentCaptureId = entered.captureId end
            Adapter.Request()
        else
            app.store:Observe(Adapter.Identity(), map, nil, Adapter.Time())
        end
    elseif stage ~= "ARMED" then
        app.store:Fail("EARLY_EXIT", Adapter.Time())
    end
    changed(stage)
end
local function scores(isFresh)
    updateContext()
    if context ~= true or not app.store or app.store.error then return end
    local record = app.store:Active()
    if not record or record.capture.stage == "ARMED" then return end
    local oldStage = record.capture.stage
    if isFresh and cleanEntry then freshScores = true end
    local winner = Adapter.Winner()
    if oldStage == "RECORDING" and freshScores and (winner == 0 or winner == 1) then
        app.store:BeginFinal(); finalElapsed = 0
    end
    record = app.store:Active()
    if not record then return end
    local roster = Adapter.Roster()
    if record.capture.stage == "FINAL_PENDING" then
        if freshScores and (winner == 0 or winner == 1) and roster and #roster > 0 then
            app.store:Final(roster, winner, Adapter.Time())
        end
    elseif isFresh and roster then
        app.store:Observe(Adapter.Identity(), select(2, Adapter.Context()), roster, Adapter.Time())
    end
    changed(oldStage)
end
frame:SetScript("OnEvent", function(_, event, name, isReloadingUI)
    if event == "ADDON_LOADED" then
        if name ~= addonName then return end
        app.store = Store.New(RBGSMatchData)
        if RBGSMatchData == nil then RBGSMatchData = app.store.root end
        loaded = true
        if type(RBGSSettings) == "table" then
            reloadCheckpoint = RBGSSettings.captureCheckpoint
            RBGSSettings.captureCheckpoint = nil -- Consume once, including on normal login.
        end
    elseif event == "PLAYER_LOGIN" then
        if not loaded then return end
        loggedIn = true
        app.client, app.adapterError = Adapter.Client()
        if app.adapterError and app.store:Active() then app.store:Fail("UNSUPPORTED_ADAPTER", Adapter.Time())
        else
            local active = app.store:Active()
            restorePending = active ~= nil and active.capture.stage ~= "ARMED"
            app.store:Restore(Adapter.Identity(), Adapter.Time(), app.client, restorePending)
            restorePending = restorePending and app.store:Active() ~= nil
        end
        updateContext()
        if app.store.error or app.adapterError then app.Message(app.store.error or app.adapterError) end
        refresh()
    elseif event == "PLAYER_LOGOUT" then
        if type(RBGSSettings) ~= "table" then RBGSSettings = {} end
        RBGSSettings.captureCheckpoint = nil
        local active = app.store and app.store:Active()
        if active and active.capture.stage ~= "ARMED" and not restorePending then
            local inBG, map = Adapter.Context()
            app.store:Observe(Adapter.Identity(), map, nil, Adapter.Time())
            active = app.store:Active()
            local checkpoint = inBG and active and Adapter.SessionSnapshot()
            if checkpoint then
                checkpoint.captureId, checkpoint.revision = active.captureId, active.captureRevision
                RBGSSettings.captureCheckpoint = checkpoint
            end
        end
    elseif event == "PLAYER_ENTERING_WORLD" then
        if restorePending then
            local inBG, map = Adapter.Context()
            local resumed = app.store:Resume(Adapter.Identity(), inBG and map, Adapter.Time(), app.client,
                reloadCheckpoint, Adapter.SessionSnapshot(), name == false and isReloadingUI == true)
            restorePending, reloadCheckpoint = false, nil
            if resumed then
                context, cleanEntry, freshScores, finalElapsed = true, true, false, 0
                currentCaptureId = app.store:Active().captureId
                app.Message("Recording resumed after reload. The interruption is saved with the match data.")
                Adapter.Request()
            else app.Message("Recording could not resume safely. Check /rbgs status.") end
        end
        updateContext()
    elseif event == "ZONE_CHANGED_NEW_AREA" or event == "PVP_MATCH_ACTIVE" then
        updateContext()
    elseif event == "UPDATE_BATTLEFIELD_SCORE" then
        scores(true)
    elseif event == "PVP_MATCH_COMPLETE" or event == "PLAYER_PVP_MATCH_COMPLETE" then
        updateContext()
        local record = app.store and app.store:Active()
        if record and record.capture.stage == "RECORDING" and context == true then
            app.store:BeginFinal(); finalElapsed = 0
            -- Demand another scoreboard notification after the final request.
            freshScores = false
            Adapter.Request()
            refresh()
        end
    end
end)
frame:SetScript("OnUpdate", function(_, elapsed)
    if not loggedIn then return end
    if restorePending then
        restoreElapsed = restoreElapsed + elapsed
        if restoreElapsed > 30 then
            app.store:Fail("SESSION_BOUNDARY_UNCERTAIN", Adapter.Time(), "UNKNOWN")
            restorePending, reloadCheckpoint = false, nil
            refresh()
        end
        return
    end
    pollElapsed = pollElapsed + elapsed
    local active = app.store and app.store:Active()
    if active and active.capture.stage == "FINAL_PENDING" then finalElapsed = finalElapsed + elapsed end
    if pollElapsed < 2 then return end
    pollElapsed = 0
    updateContext()
    active = app.store and app.store:Active()
    if active and active.capture.stage == "FINAL_PENDING" then
        scores(false)
        if finalElapsed >= 30 and app.store:Active() then
            app.store:Fail("MISSING_FINAL_OUTCOME", Adapter.Time())
            changed("FINAL_PENDING")
        else Adapter.Request() end
    end
end)
for _, event in ipairs({"ADDON_LOADED", "PLAYER_LOGIN", "PLAYER_LOGOUT", "PLAYER_ENTERING_WORLD", "ZONE_CHANGED_NEW_AREA",
    "PVP_MATCH_ACTIVE", "PVP_MATCH_COMPLETE", "PLAYER_PVP_MATCH_COMPLETE", "UPDATE_BATTLEFIELD_SCORE"}) do
    local ok = pcall(frame.RegisterEvent, frame, event)
    if not ok and event == "UPDATE_BATTLEFIELD_SCORE" then app.eventError = "Cannot receive scoreboard updates. Match recording is unavailable." end
end

local stageLabels = {
    ARMED="Ready to record", RECORDING="Recording match", FINAL_PENDING="Waiting for final scoreboard",
    COMPLETE="Match recorded", INCOMPLETE="Match data incomplete",
}
local reasonLabels = {
    CAPTURE_PENDING="Recording is not finished yet", MAP_MISMATCH="The battleground changed",
    CHARACTER_CHANGED="The character changed", EARLY_EXIT="Left before the final result was saved",
    SESSION_BOUNDARY_UNCERTAIN="Recording was interrupted by a reload, logout or game update",
    MISSING_FINAL_OUTCOME="The final result could not be read", MISSING_REQUIRED_DATA="Some required match data is missing",
    UNSUPPORTED_ADAPTER="This game data cannot be read", STORAGE_FULL="Match storage is full", CANCELLED="Recording cancelled",
}
function app.Status()
    if not app.store then return "Waiting for the addon to load." end
    if app.store.error then return app.store.error end
    local lines = {app.adapterError or app.eventError or Adapter.Problem() or (app.client and app.client.product == "wow_anniversary" and "Temporary TBC Anniversary WSG capture test. Results are unverified. rbgs.io is for Forever only." or "Darkspear test matches. Tests do not change your rating."),
        "Check upload status in the companion.", "Saved recordings: " .. #app.store.root.captures .. " / 8"}
    for _, record in ipairs(app.store.root.captures) do
        local c = record.capture
        lines[#lines + 1] = stageLabels[c.stage] or "Recording status unknown"
        lines[#lines + 1] = "  " .. (reasonLabels[c.incompleteReason] or "Final scoreboard recorded") .. "  |  " .. #c.roster .. " players"
        if c.interruptions then lines[#lines + 1] = "  Reload interruptions: " .. #c.interruptions end
        lines[#lines + 1] = "  Data ID: " .. record.captureId .. "  |  version " .. record.captureRevision
    end
    return table.concat(lines, "\n")
end
function app.Reload()
    local combat = Adapter.Call(InCombatLockdown)
    if not combat then app.Message("Combat state unavailable. Use /reload manually when safe."); return false end
    if combat and combat[1] then app.Message("Leave combat before reloading."); return false end
    local active = app.store and app.store:Active()
    if active and active.capture.stage ~= "ARMED" and (restorePending or not Adapter.SessionSnapshot()) then
        app.Message("Cannot establish reload continuity for this recording. Use /reload manually only if necessary."); return false
    end
    if app.PrepareResultsReload then pcall(app.PrepareResultsReload) end
    if not Adapter.Call(ReloadUI) then
        if app.ResultsReloadFailed then pcall(app.ResultsReloadFailed) end
        app.Message("Reload unavailable. Use /reload or log out to save."); return false
    end
    return true
end
function app.ResultSaveState()
    if not currentCaptureId or not app.store or app.store.error then return false, false end
    local inBG, map = Adapter.Context()
    local winner, readable = Adapter.Winner()
    local expectedMap = app.client and app.client.product == "wow_anniversary" and 489 or 2997
    if inBG ~= true or not map or map.gameMapId ~= expectedMap or not readable or (winner ~= 0 and winner ~= 1) then return false, false end
    for _, record in ipairs(app.store.root.captures) do
        if record.captureId == currentCaptureId then
            if record.capture.stage == "FINAL_PENDING" or record.capture.stage == "RECORDING" then
                return true, false, "Waiting for the final scoreboard. Keep this window open."
            end
            if record.capture.stage ~= "COMPLETE" or record.capture.state ~= "COMPLETE" then
                return false, false
            end
            if not record.capture.map or record.capture.map.gameMapId ~= map.gameMapId
                or record.capture.map.profile ~= map.profile or record.client.product ~= app.client.product
                or record.capture.outcome.winningObservedTeamKey ~= tostring(winner) then return false, false end
            local combat = Adapter.Call(InCombatLockdown)
            if not combat or combat[1] then return true, false, "Leave combat before saving results." end
            return true, true, "Saves the match with a reload, then reopens this scoreboard so you can leave. Keep the companion open to upload the data.", record
        end
    end
    return false, false
end
function app.SaveMatchResults()
    local visible, ready, reason = app.ResultSaveState()
    if not visible or not ready then app.Message(reason or "No completed RBGS recording is ready to save."); return false end
    app.Message("Saving match data. The companion will upload it when connected and uploads are enabled.")
    return app.Reload()
end
function app.CompletedMatches()
    local records = {}
    if not app.store or app.store.error then return records end
    for _, record in ipairs(app.store.root.captures) do
        if record.capture.stage == "COMPLETE" and record.capture.state == "COMPLETE" then records[#records+1] = record end
    end
    table.sort(records, function(a,b)
        if a.capture.endedAt == b.capture.endedAt then return a.captureId < b.captureId end
        return a.capture.endedAt > b.capture.endedAt
    end)
    return records
end
function app.HistoryText(index)
    if app.store and app.store.error then return app.store.error end
    local records = app.CompletedMatches()
    if #records == 0 then return "No completed matches recorded yet.\nCheck uploads in the companion. Results still need to be verified." end
    local record = records[math.max(1, math.min(index or 1, #records))]
    local c = record.capture
    local team = c.outcome.winningObservedTeamKey == "0" and "Horde" or "Alliance"
    local lines = {"COMPLETED MATCH " .. math.max(1, math.min(index or 1, #records)) .. " / " .. #records,
        c.map.observedName .. "  |  " .. team .. " won  |  " .. #c.roster .. " players",
        "Started (UTC): " .. c.startedAt, "Ended (UTC): " .. c.endedAt,
        "Character in saved data: " .. record.observedCharacter.name,
        "Data ID: " .. record.captureId .. "  |  version " .. record.captureRevision,
        "Check uploads in the companion. Result not yet verified.", "", "FINAL SCOREBOARD"}
    if c.interruptions then table.insert(lines, 2, "Resumed after reload; recorded interruptions: " .. #c.interruptions) end
    for _, row in ipairs(c.roster) do
        local faction = row.observedTeamKey == "0" and "Horde" or row.observedTeamKey == "1" and "Alliance" or "Unknown team"
        lines[#lines+1] = row.character.name .. "  /  " .. faction
        local stats = {}
        for _, field in ipairs({{"killingBlows","KB"},{"honorableKills","HK"},{"deaths","Deaths"},{"damage","Damage"},{"healing","Healing"},{"flagsCaptured","Flags captured"},{"flagsReturned","Flags returned"}}) do
            stats[#stats+1] = field[2] .. ": " .. (row[field[1]] ~= nil and tostring(row[field[1]]) or "Unknown")
        end
        lines[#lines+1] = "  " .. table.concat(stats, "  |  ")
    end
    return table.concat(lines,"\n")
end
SLASH_RBGS1 = "/rbgs"
SlashCmdList.RBGS = function(command)
    local action, argument = (command or ""):match("^%s*(%S*)%s*(.-)%s*$")
    action = action:lower()
    if action == "match" or action == "test-wsg" then
        if not loggedIn or not app.store then app.Message("Wait for your character to log in before entering the match command."); return end
        if app.adapterError or app.eventError then app.Message(app.adapterError or app.eventError); return end
        if (action == "test-wsg") ~= (app.client and app.client.product == "wow_anniversary") then
            app.Message("Copy the command for this client from the companion. TBC Anniversary accepts only explicit WSG test commands."); return
        end
        updateContext()
        local _, message = app.store:Arm(argument, Adapter.Identity(), app.client, Adapter.Context())
        app.Message(message); refresh()
    elseif action == "status" then
        app.Message(app.Status())
    elseif action == "cancel" then
        if app.store and app.store:Fail("CANCELLED", Adapter.Time()) then
            app.Message("Recording cancelled. Your data is kept. Use /reload to save it, then request a new test match.")
        else app.Message("No match recording is active.") end
        refresh()
    elseif action == "reload" then app.Reload()
    elseif action == "history" then if app.ShowHistory then app.ShowHistory() end
    elseif action == "" or action == "show" then if app.ShowPanel then app.ShowPanel() end
    else app.Message("Commands: match <token>, test-wsg <token>, status, history, show, cancel, reload. Saved match data cannot be deleted here.") end
end
