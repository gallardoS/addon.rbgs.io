local addonName, probe = ...
local LOGO = "Interface\\AddOns\\" .. addonName .. "\\Media\\logo"
local GOLD = { 250 / 255, 204 / 255, 21 / 255 }
local LIGHT = { 250 / 255, 250 / 255, 246 / 255 }
local MUTED = { 0.65, 0.68, 0.68 }
local PANEL_WIDTH, PANEL_HEIGHT = 660, 620

local function clean(value, fallback)
    local text = probe.Printable(value)
    if not text or text == "<nil or protected>" then return fallback or "Unknown" end
    return text:gsub("|", "||"):gsub("[\r\n]", " "):sub(1, 240)
end

local function valueAt(values, index, fallback)
    return clean(values and values[index], fallback)
end

local function text(parent, font, x, y, width, color)
    local label = parent:CreateFontString(nil, "OVERLAY", font)
    label:SetPoint("TOPLEFT", x, y)
    label:SetWidth(width)
    label:SetJustifyH("LEFT")
    label:SetJustifyV("TOP")
    label:SetTextColor(unpack(color or LIGHT))
    return label
end

local function background(parent, red, green, blue, alpha)
    local fill = parent:CreateTexture(nil, "BACKGROUND")
    fill:SetAllPoints(parent)
    fill:SetColorTexture(red, green, blue, alpha or 1)
    return fill
end

local function button(parent, name, label, x, y, width, action, primary)
    local control = CreateFrame("Button", name, parent)
    control:SetSize(width, 34)
    control:SetPoint("TOPLEFT", x, y)
    background(control, primary and GOLD[1] or 0.09, primary and GOLD[2] or 0.10,
        primary and GOLD[3] or 0.10)
    local highlight = control:CreateTexture(nil, "HIGHLIGHT")
    highlight:SetAllPoints(control)
    highlight:SetColorTexture(1, 1, 1, 0.10)
    local caption = control:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    caption:SetPoint("CENTER")
    caption:SetText(label)
    caption:SetTextColor(unpack(primary and { 0.05, 0.05, 0.03 } or LIGHT))
    control:SetScript("OnClick", action)
    return control
end

local window = CreateFrame("Frame", "RBGSProbePanel", UIParent)
window:SetSize(PANEL_WIDTH, PANEL_HEIGHT)
window:SetPoint("CENTER")
window:SetFrameStrata("DIALOG")
window:SetClampedToScreen(true)
window:SetMovable(true)
window:EnableMouse(true)
window:RegisterForDrag("LeftButton")
window:SetScript("OnDragStart", window.StartMoving)
window:SetScript("OnDragStop", window.StopMovingOrSizing)
background(window, 7 / 255, 8 / 255, 8 / 255, 0.98)
local accent = window:CreateTexture(nil, "ARTWORK")
accent:SetPoint("TOPLEFT")
accent:SetPoint("TOPRIGHT")
accent:SetHeight(2)
accent:SetColorTexture(unpack(GOLD))
local logo = window:CreateTexture(nil, "ARTWORK")
logo:SetSize(42, 42)
logo:SetPoint("TOPLEFT", 22, -12)
logo:SetTexture(LOGO)
text(window, "GameFontNormalLarge", 76, -20, 420):SetText("rbgs.io Debugger")
text(window, "GameFontHighlightSmall", 22, -62, 616, MUTED)
    :SetText("Automatic BG entry, 5-minute and final captures. Save with a reload.")
button(window, "RBGSProbeClose", "X", 610, -17, 28, function() window:Hide() end)
if type(UISpecialFrames) == "table" then table.insert(UISpecialFrames, "RBGSProbePanel") end

local environment = CreateFrame("Frame", nil, window)
environment:SetSize(616, 86)
environment:SetPoint("TOPLEFT", 22, -90)
background(environment, 0.065, 0.075, 0.075)
local characterText = text(environment, "GameFontNormalLarge", 14, -12, 580)
local mapText = text(environment, "GameFontHighlight", 14, -36, 580, GOLD)
local buildText = text(environment, "GameFontHighlightSmall", 14, -61, 580, MUTED)

local function stat(x, heading)
    local card = CreateFrame("Frame", nil, window)
    card:SetPoint("TOPLEFT", x, -188)
    card:SetSize(197, 70)
    background(card, 0.065, 0.075, 0.075)
    text(card, "GameFontHighlightSmall", 12, -10, 175, MUTED):SetText(heading)
    return text(card, "GameFontNormalLarge", 12, -33, 175)
end
local recordText = stat(22, "RETAINED RECORDS")
local scoreText = stat(231, "LATEST SCOREBOARD ROWS")
local winnerText = stat(440, "RAW WINNER (UNVERIFIED)")

local notice = text(window, "GameFontHighlightSmall", 22, -348, 616, GOLD)
local reloadButton
local clearButton
button(window, "RBGSProbeRefresh", "Refresh view", 22, -274, 197,
    function() probe.Refresh() end)
local function reload(clearHistory)
    if type(InCombatLockdown) == "function" and InCombatLockdown() then
        notice:SetText("Leave combat before saving with a reload.")
        return
    end
    if type(ReloadUI) ~= "function" then
        notice:SetText("Reload unavailable. History preserved; use /reload outside combat.")
        return
    end
    local previous = RBGSCompatibilityData
    if clearHistory then RBGSCompatibilityData = { schema = 1, records = {} } end
    local _, errorMessage = probe.SafeCall(ReloadUI)
    if errorMessage then
        if clearHistory then RBGSCompatibilityData = previous end
        notice:SetText("Reload failed. History preserved; use /reload outside combat.")
    end
end
reloadButton = button(window, "RBGSProbeReload", "Save / reload", 231, -274, 197,
    function() reload(false) end, true)
clearButton = button(window, "RBGSProbeClear", "Clear history / reload", 440, -274, 197,
    function() reload(true) end)
text(window, "GameFontHighlightSmall", 22, -319, 616, MUTED)
    :SetText("Clear history deletes all local probe records. Save / reload keeps them.")

local detailsPanel = CreateFrame("Frame", nil, window)
detailsPanel:SetPoint("TOPLEFT", 22, -376)
detailsPanel:SetSize(616, 184)
background(detailsPanel, 0.065, 0.075, 0.075)
text(detailsPanel, "GameFontNormal", 12, -10, 570):SetText("CAPTURE DETAILS  /  SCROLL FOR RAW SCOREBOARD")
local scroll = CreateFrame("ScrollFrame", "RBGSProbeDetailsScroll", detailsPanel)
scroll:SetPoint("TOPLEFT", 12, -34)
scroll:SetSize(592, 138)
scroll:EnableMouseWheel(true)
local content = CreateFrame("Frame", nil, scroll)
content:SetSize(572, 138)
scroll:SetScrollChild(content)
local details = text(content, "GameFontHighlightSmall", 0, 0, 572, MUTED)
scroll:SetScript("OnMouseWheel", function(self, delta)
    self:SetVerticalScroll(math.max(0, math.min(self:GetVerticalScrollRange(), self:GetVerticalScroll() - delta * 28)))
end)
text(window, "GameFontHighlightSmall", 22, -574, 616, MUTED)
    :SetText("Only the newest 300 records are retained. Save the final capture before leaving.\nLocal diagnostics; no upload, rating or verified match result.")

local launcher = CreateFrame("Button", "RBGSProbeLauncher", Minimap or UIParent)
launcher:SetSize(31, 31)
launcher:EnableMouse(true)
launcher:RegisterForClicks("LeftButtonUp")
launcher:RegisterForDrag("LeftButton")
launcher:SetFrameStrata("HIGH")
launcher:SetFrameLevel((Minimap and Minimap:GetFrameLevel() or UIParent:GetFrameLevel()) + 20)
launcher:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")
local launcherBackground = launcher:CreateTexture(nil, "BACKGROUND")
launcherBackground:SetSize(20, 20)
launcherBackground:SetPoint("TOPLEFT", 7, -5)
launcherBackground:SetTexture("Interface\\Minimap\\UI-Minimap-Background")
local launcherIcon = launcher:CreateTexture(nil, "ARTWORK")
launcherIcon:SetSize(20, 20)
launcherIcon:SetPoint("TOPLEFT", 7, -5)
launcherIcon:SetTexture(LOGO)
local launcherBorder = launcher:CreateTexture(nil, "OVERLAY")
launcherBorder:SetSize(53, 53)
launcherBorder:SetPoint("TOPLEFT")
launcherBorder:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
launcher:SetScript("OnClick", function(self)
    if self.dragging then return end
    if window:IsShown() then window:Hide() else probe.ShowPanel() end
end)
local function launcherSettings()
    if type(RBGSDebuggerSettings) ~= "table" then RBGSDebuggerSettings = {} end
    local angle = RBGSDebuggerSettings.minimapAngle
    if type(angle) ~= "number" or angle ~= angle or math.abs(angle) == math.huge then angle = 225 end
    RBGSDebuggerSettings.minimapAngle = angle % 360
    return RBGSDebuggerSettings
end
local function positionLauncher()
    launcher:ClearAllPoints()
    if Minimap then
        local angle = math.rad(launcherSettings().minimapAngle)
        local radius = math.max(Minimap:GetWidth(), Minimap:GetHeight()) / 2 + 8
        launcher:SetPoint("CENTER", Minimap, "CENTER", math.cos(angle) * radius, math.sin(angle) * radius)
    else
        launcher:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", -36, -240)
    end
end
launcher:RegisterEvent("PLAYER_LOGIN")
launcher:SetScript("OnEvent", positionLauncher)
positionLauncher()
launcher:SetScript("OnDragStart", function(self)
    if not Minimap then return end
    self.dragging = true
    if GameTooltip then GameTooltip:Hide() end
    self:SetScript("OnUpdate", function()
        local x, y = GetCursorPosition()
        local centerX, centerY = Minimap:GetCenter()
        if not centerX or not centerY then return end
        local scale = Minimap:GetEffectiveScale()
        launcherSettings().minimapAngle = math.deg(math.atan2(y / scale - centerY, x / scale - centerX)) % 360
        positionLauncher()
    end)
end)
launcher:SetScript("OnDragStop", function(self)
    self:SetScript("OnUpdate", nil)
    self.dragging = false
end)
launcher:SetClampedToScreen(true)
launcher:SetScript("OnEnter", function(self)
    if not GameTooltip then return end
    GameTooltip:SetOwner(self, "ANCHOR_LEFT")
    GameTooltip:SetText("rbgs.io Debugger")
    GameTooltip:AddLine("Left-click to open. Drag to move around the minimap.", 1, 1, 1)
    GameTooltip:Show()
end)
launcher:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)

local function stamp(record)
    if not record then return "Not captured" end
    if type(date) == "function" and type(record.at) == "number" then return date("%H:%M:%S", record.at) end
    return clean(record.at)
end

probe.Refresh = function()
    if not window:IsShown() then return end
    local latest, count = probe.LatestRecords()
    local identity = latest.identity and latest.identity.payload or {}
    local location = latest.environment and latest.environment.payload or {}
    local scoreboard = latest.scoreboard and latest.scoreboard.payload
    local marker = latest.capture_marker and latest.capture_marker.payload
    characterText:SetText(valueAt(identity.name, 1, "Character not captured") .. "  /  " .. valueAt(identity.realm, 1))
    mapText:SetText("Latest environment: " .. valueAt(location.instance, 1, "Not captured"))
    buildText:SetText("Build " .. valueAt(location.build, 2) .. "  |  Interface " .. valueAt(location.build, 4)
        .. "  |  Environment captured " .. stamp(latest.environment))
    recordText:SetText(count .. " / " .. probe.MaxRecords)
    scoreText:SetText(scoreboard and not scoreboard.countError and clean(scoreboard.count) or "Unavailable")
    winnerText:SetText(scoreboard and not scoreboard.winnerError and valueAt(scoreboard.winner, 1) or "Unknown")
    notice:SetText(marker and ("Latest capture: " .. clean(marker.phase) .. " at " .. stamp(latest.capture_marker)
        .. ". In memory; use Save / reload to flush.") or "Waiting for a BG. Captures run automatically; reload remains manual.")

    local lines = { "Environment: " .. stamp(latest.environment) .. "   |   Scoreboard: " .. stamp(latest.scoreboard) }
    local restored = latest.session_restored and latest.session_restored.payload
    lines[#lines + 1] = "Records restored at load: " .. (restored and clean(restored.existingRecords) or "Unknown")
    local records = RBGSCompatibilityData and RBGSCompatibilityData.records or {}
    local captures = 0
    lines[#lines + 1] = "Recent captures (newest first):"
    for index = #records, 1, -1 do
        if records[index].kind == "capture_marker" then
            lines[#lines + 1] = "  " .. stamp(records[index]) .. "  " .. clean(records[index].payload.phase)
            captures = captures + 1
            if captures == 6 then break end
        end
    end
    if captures == 0 then lines[#lines + 1] = "  None yet" end
    local roster = latest.group_roster and latest.group_roster.payload
    lines[#lines + 1] = "Group reported count: " .. (roster and clean(roster.reportedCount) or "Not captured")
    if scoreboard then
        lines[#lines + 1] = "Scoreboard rows retained: " .. #(scoreboard.rows or {}) .. " / " .. clean(scoreboard.count)
        if scoreboard.countError then lines[#lines + 1] = "Score count: " .. clean(scoreboard.countError) end
        if scoreboard.winnerError then lines[#lines + 1] = "Winner: " .. clean(scoreboard.winnerError) end
        lines[#lines + 1] = "Raw positional returns below. Field meanings and winner encoding are unverified."
        for _, row in ipairs(scoreboard.rows or {}) do
            local fields = {}
            for index = 1, math.min(row.values and row.values.count or 0, 24) do
                fields[#fields + 1] = index .. "=" .. valueAt(row.values, index)
            end
            lines[#lines + 1] = "Row " .. clean(row.index) .. ": " .. (row.error and clean(row.error) or table.concat(fields, ", "))
        end
    else
        lines[#lines + 1] = "No scoreboard captured. Open the in-game scoreboard, let it load, then capture."
    end
    local capabilities = latest.capabilities and latest.capabilities.payload
    if capabilities then
        lines[#lines + 1] = "\nAPI CHECK (" .. stamp(latest.capabilities) .. ")"
        for _, name in ipairs({ "GetNumBattlefieldScores", "GetBattlefieldScore", "GetBattlefieldWinner", "RequestBattlefieldScoreData" }) do
            lines[#lines + 1] = name .. ": " .. clean(capabilities[name])
        end
    end
    local registrations = latest.event_registration and latest.event_registration.payload
    if registrations then
        lines[#lines + 1] = "\nEVENT REGISTRATION"
        for _, name in ipairs({ "PVP_MATCH_ACTIVE", "PVP_MATCH_COMPLETE", "UPDATE_BATTLEFIELD_SCORE" }) do
            lines[#lines + 1] = name .. ": " .. clean(registrations[name])
        end
    end
    details:SetText(table.concat(lines, "\n"))
    content:SetHeight(math.max(138, details:GetStringHeight() + 10))
    local inCombat = type(InCombatLockdown) == "function" and InCombatLockdown()
    reloadButton:SetEnabled(not inCombat)
    reloadButton:SetAlpha(inCombat and 0.45 or 1)
    clearButton:SetEnabled(not inCombat)
    clearButton:SetAlpha(inCombat and 0.45 or 1)
end

probe.ShowPanel = function()
    local availableWidth = UIParent:GetWidth() - 40
    local availableHeight = UIParent:GetHeight() - 40
    window:SetScale(math.max(0.4, math.min(1, availableWidth / PANEL_WIDTH, availableHeight / PANEL_HEIGHT)))
    window:Show()
    probe.Refresh()
end
window:SetScript("OnShow", function() probe.Refresh() end)
window:SetScript("OnEvent", function() probe.Refresh() end)
for _, event in ipairs({ "PLAYER_REGEN_DISABLED", "PLAYER_REGEN_ENABLED" }) do
    pcall(window.RegisterEvent, window, event)
end
window:Hide()
