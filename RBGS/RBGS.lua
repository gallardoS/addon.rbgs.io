local addonName, app = ...
local Store, Adapter = app.Store, app.Adapter
local frame = CreateFrame("Frame", "RBGSCaptureEvents")
local loaded, loggedIn, context, cleanEntry, freshScores = false, false, nil, false, false
local pollElapsed, finalElapsed = 0, 0

function app.Message(message)
    if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage("rbgs.io: " .. message) end
end
local function refresh() if app.Refresh then app.Refresh() end end
local function changed(oldStage)
    local active = app.store and app.store:Active()
    if oldStage and not active then
        app.Message("Attempt ended. Use /reload before leaving to save the capture; inspect /rbgs status.")
    end
    refresh()
end
local function updateContext()
    if not loggedIn or not app.store or app.store.error then return end
    local inBG, map = Adapter.Context()
    if inBG == nil then return end
    local wasBG = context
    context = inBG
    local record = app.store:Active()
    if not record then return end
    local stage = record.capture.stage
    if inBG then
        if stage == "ARMED" then
            local winner, readable = Adapter.Winner()
            cleanEntry = wasBG == false and readable and winner == nil
            freshScores, finalElapsed = false, 0
            app.store:Enter(Adapter.Identity(), map, Adapter.Time(), cleanEntry)
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
frame:SetScript("OnEvent", function(_, event, name)
    if event == "ADDON_LOADED" then
        if name ~= addonName then return end
        app.store = Store.New(RBGSMatchData)
        if RBGSMatchData == nil then RBGSMatchData = app.store.root end
        loaded = true
    elseif event == "PLAYER_LOGIN" then
        if not loaded then return end
        loggedIn = true
        app.client, app.adapterError = Adapter.Client()
        if app.adapterError and app.store:Active() then app.store:Fail("UNSUPPORTED_ADAPTER", Adapter.Time())
        else app.store:Restore(Adapter.Identity(), Adapter.Time(), app.client) end
        updateContext()
        if app.store.error or app.adapterError then app.Message(app.store.error or app.adapterError) end
        refresh()
    elseif event == "PLAYER_ENTERING_WORLD" or event == "ZONE_CHANGED_NEW_AREA" or event == "PVP_MATCH_ACTIVE" then
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
for _, event in ipairs({"ADDON_LOADED", "PLAYER_LOGIN", "PLAYER_ENTERING_WORLD", "ZONE_CHANGED_NEW_AREA",
    "PVP_MATCH_ACTIVE", "PVP_MATCH_COMPLETE", "PLAYER_PVP_MATCH_COMPLETE", "UPDATE_BATTLEFIELD_SCORE"}) do
    local ok = pcall(frame.RegisterEvent, frame, event)
    if not ok and event == "UPDATE_BATTLEFIELD_SCORE" then app.eventError = "Scoreboard event unavailable; capture disabled." end
end

function app.Status()
    if not app.store then return "Waiting for addon load." end
    if app.store.error then return app.store.error end
    local lines = {app.adapterError or app.eventError or Adapter.Problem() or "Darkspear test matches. Tests do not change your rating.",
        "Stored attempts: " .. #app.store.root.captures .. " / 8"}
    for _, record in ipairs(app.store.root.captures) do
        local c = record.capture
        lines[#lines + 1] = record.captureId .. "  |  revision " .. record.captureRevision .. "  |  " .. c.stage
        lines[#lines + 1] = "  " .. (c.incompleteReason or "Final observation captured") .. "  |  rows " .. #c.roster
    end
    return table.concat(lines, "\n")
end
function app.Reload()
    local combat = Adapter.Call(InCombatLockdown)
    if not combat then app.Message("Combat state unavailable. Use /reload manually when safe."); return end
    if combat and combat[1] then app.Message("Leave combat before reloading."); return end
    local active = app.store and app.store:Active()
    if active and active.capture.stage ~= "ARMED" then
        app.Message("Reload interrupts this attempt. It will restore as INCOMPLETE; use /reload manually only if necessary."); return
    end
    if not Adapter.Call(ReloadUI) then app.Message("Reload unavailable. Use /reload or log out to save.") end
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
    if #records == 0 then return "No completed matches yet.\nLocal captures are not verified or uploaded." end
    local record = records[math.max(1, math.min(index or 1, #records))]
    local c = record.capture
    local team = c.outcome.winningObservedTeamKey == "0" and "Horde" or "Alliance"
    local lines = {"COMPLETED MATCH " .. math.max(1, math.min(index or 1, #records)) .. " / " .. #records,
        c.map.observedName .. "  |  " .. team .. " won  |  " .. #c.roster .. " players",
        "Entry (UTC): " .. c.startedAt, "Final (UTC): " .. c.endedAt,
        "Observed character: " .. record.observedCharacter.name,
        "Capture: " .. record.captureId .. "  |  revision " .. record.captureRevision,
        "Local observation; not verified or uploaded.", "", "FINAL SCOREBOARD"}
    for _, row in ipairs(c.roster) do
        local faction = row.observedTeamKey == "0" and "Horde" or row.observedTeamKey == "1" and "Alliance" or "Unknown team"
        lines[#lines+1] = row.character.name .. "  /  " .. faction
        local stats = {}
        for _, field in ipairs({{"killingBlows","KB"},{"honorableKills","HK"},{"deaths","Deaths"},{"damage","Damage"},{"healing","Healing"}}) do
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
    if action == "match" then
        if not loggedIn or not app.store then app.Message("Wait for login before arming."); return end
        if app.adapterError or app.eventError then app.Message(app.adapterError or app.eventError); return end
        updateContext()
        local _, message = app.store:Arm(argument, Adapter.Identity(), app.client, Adapter.Context())
        app.Message(message); refresh()
    elseif action == "status" then
        app.Message(app.Status())
    elseif action == "cancel" then
        if app.store and app.store:Fail("CANCELLED", Adapter.Time()) then
            app.Message("Attempt cancelled and retained. Use /reload to save; request a fresh assignment.")
        else app.Message("No active attempt.") end
        refresh()
    elseif action == "reload" then app.Reload()
    elseif action == "history" then if app.ShowHistory then app.ShowHistory() end
    elseif action == "" or action == "show" then if app.ShowPanel then app.ShowPanel() end
    else app.Message("Commands: match <token>, status, history, show, cancel, reload. Stored captures cannot be cleared here.") end
end
