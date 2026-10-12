local _, app = ...
local Adapter = {}
app.Adapter = Adapter
local Store = app.Store

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
function Adapter.Client()
    local build = Adapter.Call(GetBuildInfo)
    if not build or stringValue(build[1]) ~= "1.60.1" or stringValue(build[2]) ~= "70338" or numberValue(build[4]) ~= 16001 then
        return nil, "Unsupported client. This test addon supports Forever 1.60.1 / 70338 / 16001 only."
    end
    for _, name in ipairs({"GetInstanceInfo", "UnitName", "GetRealmName", "GetNumBattlefieldScores", "GetBattlefieldScore", "GetBattlefieldWinner"}) do
        if type(_G[name]) ~= "function" then return nil, "Required game API unavailable: " .. name end
    end
    return {addonVersion="0.1.0-test", adapterVersion="darkspear-70338-test-1", product="wow_classic_beta",
        gameVersion="1.60.1", gameBuild="70338", interface=16001}
end
function Adapter.Identity()
    local name = Adapter.Call(UnitName, "player")
    local realm = Adapter.Call(GetRealmName)
    local guid = Adapter.Call(UnitGUID, "player")
    if not name or not stringValue(name[1]) then return nil end
    return {name=stringValue(name[1]), realm=realm and stringValue(realm[1]), guid=guid and stringValue(guid[1])}
end
function Adapter.Context()
    local values = Adapter.Call(GetInstanceInfo)
    if not values or not stringValue(values[2]) then return nil end
    if values[2] ~= "pvp" then return false end
    return true, {profile="DARKSPEAR_DIAGNOSTIC", observedName=stringValue(values[1]), gameMapId=numberValue(values[8])}
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
    if not winner then return nil, false end
    return numberValue(winner[1]), true
end
function Adapter.Roster()
    local count = Adapter.Call(GetNumBattlefieldScores)
    local total = count and numberValue(count[1])
    if not total or total > 40 then return nil end
    local rows = {}
    for index = 1, total do
        local values = Adapter.Call(GetBattlefieldScore, index)
        local name = values and stringValue(values[1])
        if not name then return nil end
        -- The existing real 70338 fixture validates basic positions only.
        -- Do not infer objectives, class, GUID or draw codes from other clients.
        local character, realm = name:match("^([^%-]+)%-(.+)$")
        local team = numberValue(values[6])
        rows[index] = {character={name=character or name, realm=realm},
            observedTeamKey=(team == 0 or team == 1) and tostring(team) or nil,
            killingBlows=numberValue(values[2]), honorableKills=numberValue(values[3]), deaths=numberValue(values[4]),
            damage=numberValue(values[10]), healing=numberValue(values[11])}
    end
    return rows
end
function Adapter.Request() Adapter.Call(RequestBattlefieldScoreData) end
