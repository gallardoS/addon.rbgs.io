local _, app = ...
local Adapter = {}
app.Adapter = Adapter
local Store = app.Store
local problems = {}

function Adapter.Problem()
    for _, key in ipairs({"identity", "context", "winner", "scoreboard"}) do
        if problems[key] then return problems[key] end
    end
end

local function unreadable(key, message)
    problems[key] = message
    return nil
end

function Adapter.Call(fn, ...)
    if type(fn) ~= "function" then return nil end
    local function pack(...) return {count=select("#", ...), ...} end
    local ok, values = pcall(function(...) return pack(fn(...)) end, ...)
    return ok and values or nil
end
local function stringValue(value)
    local ok, result = pcall(function() if Store.Text(value) then return value end end)
    return ok and result or nil
end
local function numberValue(value)
    local ok, result = pcall(function() if Store.Integer(value) then return value end end)
    return ok and result or nil
end
local function optionalNumber(value)
    local ok, valid = pcall(function() return value == nil or Store.Integer(value) end)
    return ok and valid
end
local function optionalTeam(value)
    local ok, valid = pcall(function() return value == nil or value == 0 or value == 1 end)
    return ok and valid
end
function Adapter.Client()
    local build = Adapter.Call(GetBuildInfo)
    local version, revision, interface = build and stringValue(build[1]), build and stringValue(build[2]), build and numberValue(build[4])
    if not Store.GameVersion(version) or not Store.GameBuild(revision) or not interface or interface == 0 then
        return nil, "Cannot read your game version. Check that the addon loaded correctly."
    end
    for _, name in ipairs({"GetInstanceInfo", "UnitName", "GetRealmName", "GetNumBattlefieldScores", "GetBattlefieldScore", "GetBattlefieldWinner", "RequestBattlefieldScoreData"}) do
        if type(_G[name]) ~= "function" then return nil, "WoW cannot provide data needed to record matches: " .. name end
    end
    local anniversary = version:match("^2%.5%.") ~= nil
    if anniversary and (not WOW_PROJECT_BURNING_CRUSADE_CLASSIC or WOW_PROJECT_ID ~= WOW_PROJECT_BURNING_CRUSADE_CLASSIC) then
        return nil, "Cannot identify the TBC test client. Match recording is unavailable."
    end
    if not anniversary and not version:match("^1%.") then return nil, "This client is not supported for match recording." end
    return {addonVersion="0.2.0-test", adapterVersion=anniversary and "tbc-anniversary-wsg-test-v1" or "darkspear-scoreboard-v1", product=anniversary and "wow_anniversary" or "wow_classic_beta",
        gameVersion=version, gameBuild=revision, interface=interface}
end
function Adapter.Identity()
    local name = Adapter.Call(UnitName, "player")
    local realm = Adapter.Call(GetRealmName)
    local guid = Adapter.Call(UnitGUID, "player")
    -- On the tested Forever 70338 client, UnitName returns given name and surname.
    -- GetRealmName supplies the realm independently; a missing surname stays unknown.
    local givenName = name and stringValue(name[1])
    local surname = name and stringValue(name[2])
    if app.client and app.client.product == "wow_anniversary" then
        -- Classic's second return is a realm, never a Forever surname.
        if not givenName or not realm or not stringValue(realm[1]) then
            return unreadable("identity", "Cannot read your character and realm for the WSG test.")
        end
        problems.identity = nil
        return {name=givenName, realm=stringValue(realm[1]), guid=guid and stringValue(guid[1])}
    end
    if not givenName or not surname or name.count ~= 2 then
        return unreadable("identity", "Cannot read your full character name. Match recording is unavailable.")
    end
    local fullName = stringValue(givenName .. " " .. surname)
    if not fullName then return unreadable("identity", "Your character name is too long to record.") end
    problems.identity = nil
    return {name=fullName, realm=realm and stringValue(realm[1]), guid=guid and stringValue(guid[1])}
end
function Adapter.Context()
    local values = Adapter.Call(GetInstanceInfo)
    if not values or not stringValue(values[2]) then return unreadable("context", "Cannot tell whether you are in a battleground.") end
    problems.context = nil
    if values[2] ~= "pvp" then return false end
    if not stringValue(values[1]) or not numberValue(values[8]) then
        return unreadable("context", "Cannot read the battleground name or map ID.")
    end
    return true, {profile=app.client and app.client.product == "wow_anniversary" and "TBC_ANNIVERSARY_WSG_TEST" or "DARKSPEAR_DIAGNOSTIC", observedName=stringValue(values[1]), gameMapId=numberValue(values[8])}
end
function Adapter.Time()
    local stamp = Adapter.Call(GetServerTime)
    if not stamp or not numberValue(stamp[1]) then stamp = Adapter.Call(time) end
    if not stamp or not numberValue(stamp[1]) then return nil end
    local formatted = Adapter.Call(date, "!%Y-%m-%dT%H:%M:%SZ", stamp[1])
    return formatted and stringValue(formatted[1]) or nil
end
function Adapter.Winner()
    local winner = Adapter.Call(GetBattlefieldWinner)
    if not winner or winner.count > 1 or not optionalTeam(winner[1]) then
        unreadable("winner", "Cannot read the battleground result yet. Waiting for an update.")
        return nil, false
    end
    problems.winner = nil
    return winner[1], true
end
function Adapter.Roster()
    local count = Adapter.Call(GetNumBattlefieldScores)
    local total = count and numberValue(count[1])
    if not total or total > 40 then return unreadable("scoreboard", "Cannot read the number of players in the scoreboard.") end
    -- TBC retains rank at position 7, so classToken is 10 and damage/healing
    -- are 11/12. Forever's observed 70338 layout uses damage/healing at 10/11.
    local damagePosition = app.client and app.client.product == "wow_anniversary" and 11 or 10
    local healingPosition = damagePosition + 1
    local rows = {}
    for index = 1, total do
        local values = Adapter.Call(GetBattlefieldScore, index)
        local name = values and stringValue(values[1])
        if not name or values.count < 6 then return unreadable("scoreboard", "Cannot read the scoreboard player details.") end
        -- The existing real 70338 fixture validates basic positions only.
        -- Do not infer objectives, class, GUID or draw codes from other clients.
        local character, realm = name:match("^([^%-]+)%-(.+)$")
        local team = numberValue(values[6])
        if not optionalTeam(values[6]) then return unreadable("scoreboard", "Cannot read the teams in the scoreboard.") end
        for _, position in ipairs({2, 3, 4, damagePosition, healingPosition}) do
            if not optionalNumber(values[position]) then
                return unreadable("scoreboard", "Cannot read the scoreboard statistics. Your saved match data is kept.")
            end
        end
        rows[index] = {character={name=character or name, realm=realm},
            observedTeamKey=(team == 0 or team == 1) and tostring(team) or nil,
            killingBlows=numberValue(values[2]), honorableKills=numberValue(values[3]), deaths=numberValue(values[4]),
            damage=numberValue(values[damagePosition]), healing=numberValue(values[healingPosition])}
    end
    problems.scoreboard = nil
    return rows
end
function Adapter.Request() Adapter.Call(RequestBattlefieldScoreData) end
