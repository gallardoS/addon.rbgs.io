local _, app = ...
local Store = {}
app.Store = Store
Store.MAX_CAPTURES, Store.MAX_BYTES = 8, 200000

local function text(value)
    if type(value) ~= "string" or #value == 0 or #value > 512 or value:find("[%z\1-\31\127]") then return false end
    -- Validate UTF-8 and the contract's 128-code-point bound, without a Lua 5.3 dependency.
    local i, count = 1, 0
    while i <= #value do
        local first = value:byte(i)
        local width = first < 128 and 1 or first >= 194 and first <= 223 and 2
            or first >= 224 and first <= 239 and 3 or first >= 240 and first <= 244 and 4
        if not width or i + width - 1 > #value then return false end
        for j = i + 1, i + width - 1 do
            local byte = value:byte(j)
            if byte < 128 or byte > 191 then return false end
        end
        local second = value:byte(i + 1)
        if width == 3 and (first == 224 and second < 160 or first == 237 and second > 159)
            or width == 4 and (first == 240 and second < 144 or first == 244 and second > 143) then return false end
        count, i = count + 1, i + width
        if count > 128 then return false end
    end
    return true
end
Store.Text = text
local function integer(value, max)
    return type(value) == "number" and value >= 0 and value <= (max or 9007199254740991) and value == math.floor(value)
end
Store.Integer = integer
local function gameVersion(value)
    return text(value) and #value <= 32 and value:match("^%d[%d%.]*$") ~= nil
        and not value:find("%.%.") and value:sub(-1) ~= "."
end
local function gameBuild(value)
    return type(value) == "string" and #value <= 10 and value:match("^%d+$") ~= nil and tonumber(value) > 0
end
Store.GameVersion, Store.GameBuild = gameVersion, gameBuild
local function uuid(value)
    if type(value) ~= "string" or #value ~= 36 then return false end
    return value:match("^%x%x%x%x%x%x%x%x%-%x%x%x%x%-%x%x%x%x%-%x%x%x%x%-%x%x%x%x%x%x%x%x%x%x%x%x$") ~= nil
end
local function code(value)
    return type(value) == "string" and #value == 16 and value:match("^[0-9A-HJKMNP-TV-Z]+$") ~= nil
end
function Store.Token(value)
    if type(value) ~= "string" or #value ~= 57 then return nil end
    local id, secret = value:match("^RB2:([^:]+):([^:]+)$")
    if uuid(id) and code(secret) then return id:lower(), secret end
end

-- Upper bound for WoW's escaped, indented table representation. Reject cycles,
-- excessive depth/nodes, non-data values and long/invalid strings before saving.
function Store.Size(value)
    local seen, nodes = {}, 0
    local function visit(item, depth)
        nodes = nodes + 1
        if nodes > 6000 or depth > 12 then error("bounded table") end
        local kind = type(item)
        if kind == "nil" then return 8 end
        if kind == "string" then
            if not text(item) then error("bounded string") end
            return #item * 4 + 16
        end
        if kind == "number" then
            if not integer(item) then error("invalid number") end
            return 40
        end
        if kind ~= "table" or getmetatable(item) or seen[item] then error("not a data table") end
        seen[item] = true
        local size = 32
        for key, child in pairs(item) do
            size = size + visit(key, depth + 1) + visit(child, depth + 1) + 64 + depth * 16
            if size > Store.MAX_BYTES then error("storage limit") end
        end
        seen[item] = nil
        return size
    end
    local ok, size = pcall(visit, value, 0)
    return ok and size or nil
end
local function copy(value)
    if type(value) ~= "table" then return value end
    local result = {}
    for key, item in pairs(value) do result[key] = copy(item) end
    return result
end
local function equal(a, b)
    if type(a) ~= type(b) then return false end
    if type(a) ~= "table" then return a == b end
    for key, value in pairs(a) do if not equal(value, b[key]) then return false end end
    for key in pairs(b) do if a[key] == nil then return false end end
    return true
end
local function keys(value, allowed)
    if type(value) ~= "table" then return false end
    local known = {}
    for key in allowed:gmatch("[^|]+") do known[key] = true end
    for key in pairs(value) do if not known[key] then return false end end
    return true
end
local function identity(value)
    return keys(value, "|name|realm|guid|") and text(value.name)
        and (value.realm == nil or text(value.realm)) and (value.guid == nil or text(value.guid))
end
local function timestamp(value)
    return type(value) == "string" and value:match("^%d%d%d%d%-%d%d%-%d%dT%d%d:%d%d:%d%dZ$") ~= nil
end
local function array(value, max)
    if type(value) ~= "table" or #value > max then return false end
    local count = 0
    for key in pairs(value) do
        if not integer(key, max) or key < 1 or key > #value then return false end
        count = count + 1
    end
    return count == #value
end
local reasons = { CAPTURE_PENDING=true, MAP_MISMATCH=true, CHARACTER_CHANGED=true, EARLY_EXIT=true,
    SESSION_BOUNDARY_UNCERTAIN=true, MISSING_FINAL_OUTCOME=true, MISSING_REQUIRED_DATA=true,
    UNSUPPORTED_ADAPTER=true, STORAGE_FULL=true, CANCELLED=true }
local pending = { ARMED=true, RECORDING=true, FINAL_PENDING=true }
function Store.Valid(record)
    if not keys(record, "|captureId|captureRevision|assignmentCode|client|observedCharacter|capture|")
        or not uuid(record.captureId) or not code(record.assignmentCode)
        or not integer(record.captureRevision, 2147483647) or record.captureRevision < 1
        or not identity(record.observedCharacter) then return false end
    local client, c = record.client, record.capture
    if not keys(client, "|addonVersion|adapterVersion|product|gameVersion|gameBuild|interface|")
        or not text(client.addonVersion) or not text(client.adapterVersion) or client.product ~= "wow_classic_beta"
        or not gameVersion(client.gameVersion) or not gameBuild(client.gameBuild)
        or not integer(client.interface) or client.interface == 0 then return false end
    if not keys(c, "|state|stage|continuity|incompleteReason|map|startedAt|endedAt|roster|outcome|")
        or not array(c.roster, 40) or c.continuity ~= "CONTINUOUS" and c.continuity ~= "UNKNOWN"
        or c.startedAt ~= nil and not timestamp(c.startedAt) or c.endedAt ~= nil and not timestamp(c.endedAt) then return false end
    if c.map ~= nil and (not keys(c.map, "|profile|observedName|gameMapId|")
        or c.map.profile ~= "DARKSPEAR_DIAGNOSTIC" or not text(c.map.observedName)
        or c.map.gameMapId ~= nil and not integer(c.map.gameMapId)) then return false end
    for _, row in ipairs(c.roster) do
        if not keys(row, "|character|observedTeamKey|killingBlows|honorableKills|deaths|damage|healing|")
            or not identity(row.character) or row.observedTeamKey ~= nil and row.observedTeamKey ~= "0" and row.observedTeamKey ~= "1" then return false end
        for _, key in ipairs({"killingBlows", "honorableKills", "deaths", "damage", "healing"}) do
            if row[key] ~= nil and not integer(row[key]) then return false end
        end
    end
    local outcome = c.outcome
    if not keys(outcome, "|kind|winningObservedTeamKey|rawWinner|")
        or outcome.kind ~= "UNKNOWN" and outcome.kind ~= "WIN"
        or outcome.rawWinner ~= nil and not text(outcome.rawWinner) then return false end
    if outcome.kind == "WIN" then
        if outcome.winningObservedTeamKey ~= "0" and outcome.winningObservedTeamKey ~= "1" then return false end
    elseif outcome.winningObservedTeamKey ~= nil then return false end
    if c.state == "COMPLETE" then
        return c.stage == "COMPLETE" and c.continuity == "CONTINUOUS" and c.incompleteReason == nil
            and c.map ~= nil and c.startedAt ~= nil and c.endedAt ~= nil and #c.roster > 0 and outcome.kind == "WIN"
    end
    return c.state == "INCOMPLETE" and (pending[c.stage] and c.incompleteReason == "CAPTURE_PENDING"
        or c.stage == "INCOMPLETE" and reasons[c.incompleteReason] and c.incompleteReason ~= "CAPTURE_PENDING")
end

function Store.New(root)
    local self = setmetatable({root=root}, {__index=Store})
    if root == nil then self.root = {schema=2, captures={}}; return self end
    if not keys(root, "|schema|captures|") or root.schema ~= 2 or not array(root.captures, Store.MAX_CAPTURES) then
        self.error = "This saved match format is not supported. Your data is kept. Back up RBGS.lua before getting help."; return self
    end
    local ids, active = {}, 0
    for _, record in ipairs(root.captures) do
        if not Store.Size(record) or not Store.Valid(record) or ids[record.captureId:lower()] then
            self.error = "Cannot read your saved match data. Your data is kept. Back up RBGS.lua before getting help."; return self
        end
        ids[record.captureId:lower()] = true
        if pending[record.capture.stage] then active = active + 1 end
    end
    if active > 1 then self.error = "More than one recording is active. Your data is kept. Get help before starting another match." end
    return self
end
function Store:Active()
    if self.error then return nil end
    for index, record in ipairs(self.root.captures) do
        if pending[record.capture.stage] then return record, index end
    end
end
function Store:Commit(index, candidate)
    local previous = self.root.captures[index]
    if previous.capture.stage == "COMPLETE" or previous.capture.stage == "INCOMPLETE" then return false end
    candidate.captureRevision = previous.captureRevision
    if equal(previous, candidate) then return true end
    if previous.captureRevision >= 2147483647 then self.error = "This recording has reached its update limit. Your saved data is kept."; return false end
    candidate.captureRevision = previous.captureRevision + 1
    local fits, valid = Store.Size(candidate), Store.Valid(candidate)
    if not fits or not valid then
        -- Keep the last safe snapshot, with a bounded terminal failure marker.
        candidate = copy(previous)
        candidate.captureRevision = previous.captureRevision + 1
        candidate.capture.state, candidate.capture.stage = "INCOMPLETE", "INCOMPLETE"
        candidate.capture.incompleteReason = fits and "MISSING_REQUIRED_DATA" or "STORAGE_FULL"
        if not Store.Size(candidate) then self.error = "Match storage is full. The previous saved version is kept."; return false end
    end
    self.root.captures[index] = candidate
    return true
end
function Store:Arm(token, character, client, inBG)
    if self.error then return false, self.error end
    if inBG ~= false then return false, "Enter your match command before entering the battleground. Wait for WoW to finish loading first." end
    local id, secret = Store.Token(token)
    if not id then return false, "Copy the full match command from the companion and paste it into WoW chat." end
    if self:Active() then return false, "A recording is already active. Finish it or use /rbgs cancel." end
    for _, record in ipairs(self.root.captures) do
        if record.captureId:lower() == id then return false, "This match command was already used. Request a new test match." end
    end
    if #self.root.captures >= Store.MAX_CAPTURES then return false, "Match storage is full (8/8 recordings). Your saved data is kept." end
    local record = {captureId=id, captureRevision=1, assignmentCode=secret, client=copy(client), observedCharacter=copy(character),
        capture={state="INCOMPLETE", stage="ARMED", continuity="CONTINUOUS", incompleteReason="CAPTURE_PENDING", roster={}, outcome={kind="UNKNOWN"}}}
    if not Store.Size(record) or not Store.Valid(record) then return false, "Cannot read the character or game details needed to record this match." end
    self.root.captures[#self.root.captures + 1] = record
    return true, "Ready to record your next Darkspear test match. Enter the battleground. Do not use /reload while recording."
end
function Store:Fail(reason, at, continuity)
    local record, index = self:Active()
    if not record then return false end
    local candidate = copy(record)
    candidate.capture.state, candidate.capture.stage = "INCOMPLETE", "INCOMPLETE"
    candidate.capture.incompleteReason, candidate.capture.endedAt = reason, at
    candidate.capture.continuity = continuity or candidate.capture.continuity
    return self:Commit(index, candidate)
end
function Store:Restore(character, at, client)
    local record = self:Active()
    if not record then return end
    if record.capture.stage ~= "ARMED" then return self:Fail("SESSION_BOUNDARY_UNCERTAIN", at, "UNKNOWN") end
    if not identity(character) or not equal(record.observedCharacter, character) then return self:Fail("CHARACTER_CHANGED", at) end
    if client and not equal(record.client, client) then return self:Fail("SESSION_BOUNDARY_UNCERTAIN", at, "UNKNOWN") end
end
function Store:Enter(character, map, at, cleanEntry)
    local record, index = self:Active()
    if not record or record.capture.stage ~= "ARMED" then return end
    if not equal(record.observedCharacter, character) then return self:Fail("CHARACTER_CHANGED", at) end
    if not map or map.profile ~= "DARKSPEAR_DIAGNOSTIC" or map.gameMapId ~= 2997 then return self:Fail("MAP_MISMATCH", at) end
    if not cleanEntry then return self:Fail("SESSION_BOUNDARY_UNCERTAIN", at, "UNKNOWN") end
    if not timestamp(at) or not text(map.observedName) then return self:Fail("MISSING_REQUIRED_DATA", at) end
    local candidate = copy(record)
    candidate.capture.map, candidate.capture.startedAt, candidate.capture.stage = copy(map), at, "RECORDING"
    return self:Commit(index, candidate)
end
function Store:Observe(character, map, roster, at)
    local record, index = self:Active()
    if not record or record.capture.stage == "ARMED" then return end
    if not equal(record.observedCharacter, character) then return self:Fail("CHARACTER_CHANGED", at) end
    if not equal(record.capture.map, map) then return self:Fail("MAP_MISMATCH", at) end
    if roster == nil then return end
    local candidate = copy(record)
    candidate.capture.roster = copy(roster)
    return self:Commit(index, candidate)
end
function Store:BeginFinal()
    local record, index = self:Active()
    if not record or record.capture.stage ~= "RECORDING" then return end
    local candidate = copy(record)
    candidate.capture.stage = "FINAL_PENDING"
    return self:Commit(index, candidate)
end
function Store:Final(roster, winner, at)
    local record, index = self:Active()
    if not record or record.capture.stage ~= "FINAL_PENDING" or not roster or #roster == 0
        or winner ~= 0 and winner ~= 1 or not timestamp(at) then return false end
    local candidate = copy(record)
    candidate.capture.roster, candidate.capture.endedAt = copy(roster), at
    candidate.capture.outcome = {kind="WIN", winningObservedTeamKey=tostring(winner), rawWinner=tostring(winner)}
    candidate.capture.state, candidate.capture.stage, candidate.capture.incompleteReason = "COMPLETE", "COMPLETE", nil
    return self:Commit(index, candidate)
end
