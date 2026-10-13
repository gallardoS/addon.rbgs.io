local addonName, probe = ...
probe = probe or {}
local frame = CreateFrame("Frame")
local MAX_RECORDS = 300
local MAX_ROWS = 40
local CAPTURE_INTERVAL = 300
local FINAL_RETRY_INTERVAL = 2
local FINAL_RETRY_WINDOW = 30
local events = {
    "ADDON_LOADED", "PLAYER_LOGIN", "PLAYER_ENTERING_WORLD", "PLAYER_LOGOUT",
    "ZONE_CHANGED_NEW_AREA", "GROUP_ROSTER_UPDATE",
    "UPDATE_BATTLEFIELD_STATUS", "PVP_MATCH_ACTIVE", "PVP_MATCH_COMPLETE",
    "PLAYER_PVP_MATCH_COMPLETE", "UPDATE_BATTLEFIELD_SCORE",
}

local function safeCall(fn, ...)
    if type(fn) ~= "function" then return nil, "missing" end
    local ok, result = pcall(function(...)
        local function pack(...) return { count = select("#", ...), ... } end
        return pack(fn(...))
    end, ...)
    if not ok then return nil, "error: " .. tostring(result) end
    return result, nil
end

local function printable(value)
    local ok, result = pcall(function()
        local kind = type(value)
        if kind == "string" or kind == "number" or kind == "boolean" then return tostring(value) end
    end)
    if ok then return result end
    return nil
end

local function safeNumber(value)
    local ok, result = pcall(tonumber, value)
    if ok then return result end
    return nil
end

local function values(result, limit)
    if not result then return nil end
    local output = {}
    output.count = result.count
    for index = 1, math.min(result.count, limit or 4) do
        output[index] = printable(result[index]) or "<nil or protected>"
    end
    return output
end

local function now()
    local result = safeCall(GetServerTime)
    return result and result[1] or time()
end

local function emit(message)
    if DEFAULT_CHAT_FRAME then DEFAULT_CHAT_FRAME:AddMessage("RBGS probe: " .. message) end
end

local panelFailureReported = false
local function refreshPanel()
    if type(probe.Refresh) ~= "function" then return end
    local ok = pcall(probe.Refresh)
    if not ok and not panelFailureReported then
        emit("panel refresh failed; diagnostic records retained. Try Refresh view.")
    end
    panelFailureReported = not ok
end

local function appendRecords(batch)
    RBGSCompatibilityData = RBGSCompatibilityData or { schema = 1, records = {} }
    local records = RBGSCompatibilityData.records
    local timestamp = now()
    for _, record in ipairs(batch) do
        records[#records + 1] = { at = timestamp, kind = record.kind, payload = record.payload }
    end
    while #records > MAX_RECORDS do table.remove(records, 1) end
    -- Rendering must not interrupt capture or expose a partially appended snapshot.
    refreshPanel()
end

local function append(kind, payload)
    appendRecords({ { kind = kind, payload = payload } })
end

local function readIdentity()
    local name, nameError = safeCall(UnitName, "player")
    local guid, guidError = safeCall(UnitGUID, "player")
    local realm, realmError = safeCall(GetRealmName)
    return {
        name = values(name), nameError = nameError,
        guid = values(guid), guidError = guidError,
        realm = values(realm), realmError = realmError,
    }
end

local function readRoster()
    local rows = {}
    local raidCount = safeCall(GetNumGroupMembers)
    local partyCount = safeCall(GetNumSubgroupMembers)
    local count = safeNumber(raidCount and raidCount[1]) or 0
    local prefix = "raid"
    if count == 0 then count = safeNumber(partyCount and partyCount[1]) or 0; prefix = "party" end
    rows[1] = { unit = "player", name = values(safeCall(UnitName, "player")), guid = values(safeCall(UnitGUID, "player")) }
    for index = 1, math.min(count, MAX_ROWS - 1) do
        local unit = prefix .. index
        rows[#rows + 1] = { unit = unit, name = values(safeCall(UnitName, unit)), guid = values(safeCall(UnitGUID, unit)) }
    end
    return { reportedCount = count, unitPrefix = prefix, rows = rows }
end

local function readScoreboard()
    local count, countError = safeCall(GetNumBattlefieldScores)
    local rows = {}
    local total = safeNumber(count and count[1]) or 0
    for index = 1, math.min(total, MAX_ROWS) do
        local result, rowError = safeCall(GetBattlefieldScore, index)
        rows[#rows + 1] = { index = index, values = values(result, 24), error = rowError }
    end
    local winner, winnerError = safeCall(GetBattlefieldWinner)
    return {
        count = total, countError = countError, rows = rows,
        winner = values(winner), winnerError = winnerError,
        note = "Return values are positional diagnostics; verify signatures against the tested build.",
    }
end

local function readEnvironment()
    local build, buildError = safeCall(GetBuildInfo)
    local map, mapError = safeCall(GetInstanceInfo)
    return { build = values(build, 8), buildError = buildError, instance = values(map, 16), instanceError = mapError }
end

local function captureCapabilities()
    local names = {
        "GetBuildInfo", "GetServerTime", "UnitName", "UnitGUID", "GetRealmName",
        "GetNumGroupMembers", "GetNumSubgroupMembers", "GetNumBattlefieldScores",
        "GetBattlefieldScore", "GetBattlefieldWinner", "GetInstanceInfo",
        "RequestBattlefieldScoreData", "CombatLogGetCurrentEventInfo",
    }
    local found = {}
    for _, name in ipairs(names) do found[name] = type(_G[name]) end
    found.C_PvP = type(C_PvP)
    found.C_PvP_RequestScoreData = type(C_PvP) == "table" and type(C_PvP.RequestScoreData) or "unavailable"
    append("capabilities", found)
end

probe.SafeCall = safeCall
probe.Printable = printable
probe.MaxRecords = MAX_RECORDS
probe.CaptureCapabilities = captureCapabilities
probe.CaptureSnapshot = function(phase)
    appendRecords({
        { kind = "environment", payload = readEnvironment() },
        { kind = "identity", payload = readIdentity() },
        { kind = "group_roster", payload = readRoster() },
        { kind = "scoreboard", payload = readScoreboard() },
        { kind = "capture_marker", payload = { phase = phase or "Manual" } },
    })
    emit("snapshot captured; use Save / reload to flush SavedVariables")
end
probe.LatestRecords = function()
    local latest = {}
    local records = RBGSCompatibilityData and RBGSCompatibilityData.records or {}
    for index = #records, 1, -1 do
        local record = records[index]
        if not latest[record.kind] then latest[record.kind] = record end
    end
    return latest, #records
end

local inBattleground, instanceKey, completed, finalPending = false, nil, false, false
local periodicElapsed, finalElapsed, retryElapsed = 0, 0, 0

local function resultAvailable(score)
    return not score.countError and not score.winnerError and score.count > 0
        and score.winner and score.winner[1] and score.winner[1] ~= "<nil or protected>"
end

local function requestScores()
    safeCall(RequestBattlefieldScoreData)
end

local function beginFinal()
    if not inBattleground or completed then return end
    completed = true
    finalElapsed, retryElapsed = 0, 0
    requestScores()
    probe.CaptureSnapshot("Automatic final result")
    local latest = probe.LatestRecords()
    finalPending = not resultAvailable(latest.scoreboard.payload)
    emit(finalPending and "match ended; waiting up to 30 seconds for final scoreboard data"
        or "final result captured; use Save / reload before leaving")
end

local function updateContext()
    local instance = safeCall(GetInstanceInfo)
    local isBG = instance and printable(instance[2]) == "pvp"
    local key = isBG and (printable(instance[8]) or printable(instance[1])) or nil
    if not isBG then
        inBattleground, instanceKey, completed, finalPending = false, nil, false, false
        periodicElapsed = 0
    elseif not inBattleground or key ~= instanceKey then
        inBattleground, instanceKey, completed, finalPending = true, key, false, false
        periodicElapsed = 0
        requestScores()
        probe.CaptureSnapshot("Automatic BG entry")
        local latest = probe.LatestRecords()
        if resultAvailable(latest.scoreboard.payload) then beginFinal() end
    end
end

frame:SetScript("OnUpdate", function(_, elapsed)
    if not inBattleground then return end
    if finalPending then
        finalElapsed, retryElapsed = finalElapsed + elapsed, retryElapsed + elapsed
        if retryElapsed < FINAL_RETRY_INTERVAL and finalElapsed < FINAL_RETRY_WINDOW then return end
        retryElapsed = 0
        local score = readScoreboard()
        if resultAvailable(score) or finalElapsed >= FINAL_RETRY_WINDOW then
            appendRecords({
                { kind = "scoreboard", payload = score },
                { kind = "capture_marker", payload = { phase = resultAvailable(score)
                    and "Automatic final result ready" or "Automatic final result unavailable" } },
            })
            finalPending = false
            emit("final observation captured; use Save / reload before leaving")
        end
    elseif not completed then
        periodicElapsed = periodicElapsed + elapsed
        if periodicElapsed < CAPTURE_INTERVAL then return end
        periodicElapsed = 0
        requestScores()
        local score = readScoreboard()
        if resultAvailable(score) then
            beginFinal()
        else
            probe.CaptureSnapshot("Automatic 5-minute capture")
        end
    end
end)

local registered = {}
frame:SetScript("OnEvent", function(_, event, ...)
    if event == "ADDON_LOADED" then
        local name = ...
        if name ~= addonName then return end
        RBGSCompatibilityData = RBGSCompatibilityData or { schema = 1, records = {} }
        append("session_restored", { existingRecords = #RBGSCompatibilityData.records })
        append("event_registration", registered)
        emit("loaded; click the rbgs button to open the capture panel")
    elseif event == "PLAYER_LOGIN" then
        captureCapabilities()
        append("environment", readEnvironment())
        append("identity", readIdentity())
        updateContext()
        if probe.ShowPanel then probe.ShowPanel() end
    else
        if event == "UPDATE_BATTLEFIELD_SCORE" or event == "GROUP_ROSTER_UPDATE"
            or event == "UPDATE_BATTLEFIELD_STATUS" then return end
        if event == "PVP_MATCH_COMPLETE" or event == "PLAYER_PVP_MATCH_COMPLETE" then
            if inBattleground and not completed then
                append("event", { name = event })
                beginFinal()
            end
            return
        end
        local args = { ... }
        local safeArgs = {}
        for index = 1, math.min(#args, 4) do safeArgs[index] = printable(args[index]) end
        append("event", { name = event, args = safeArgs })
        if event == "PLAYER_ENTERING_WORLD" or event == "ZONE_CHANGED_NEW_AREA" or event == "PVP_MATCH_ACTIVE" then
            updateContext()
        end
    end
end)

for _, event in ipairs(events) do
    local ok, errorMessage = pcall(frame.RegisterEvent, frame, event)
    registered[event] = ok and "registered" or ("unavailable: " .. tostring(errorMessage))
end

SLASH_RBGSPROBE1 = "/rbgsprobe"
SlashCmdList.RBGSPROBE = function(command)
    command = (command or ""):lower():match("^%s*(.-)%s*$")
    if command == "status" then
        emit("saved records: " .. tostring(RBGSCompatibilityData and #RBGSCompatibilityData.records or 0))
    elseif command == "capture" then
        probe.CaptureSnapshot("Manual")
    elseif command == "capabilities" then
        captureCapabilities(); emit("capability snapshot captured")
    elseif command == "" or command == "show" then
        if probe.ShowPanel then probe.ShowPanel() end
    else
        emit("commands: show, status, capabilities, capture. Saved data is private until you sanitize and export it.")
    end
end
