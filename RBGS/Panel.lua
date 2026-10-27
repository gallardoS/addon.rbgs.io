local addonName, app = ...
local LOGO = "Interface\\AddOns\\" .. addonName .. "\\Media\\logo"
local MINIMAP_LOGO = "Interface\\AddOns\\" .. addonName .. "\\Media\\logo-minimap-32.tga"
local window = CreateFrame("Frame", "RBGSProductPanel", UIParent)
window:SetSize(600, 440)
window:SetPoint("CENTER")
window:SetFrameStrata("DIALOG")
window:SetMovable(true)
window:SetClampedToScreen(true)
window:EnableMouse(true)
window:RegisterForDrag("LeftButton")
window:SetScript("OnDragStart", window.StartMoving)
window:SetScript("OnDragStop", window.StopMovingOrSizing)
local bg = window:CreateTexture(nil, "BACKGROUND")
bg:SetAllPoints()
bg:SetColorTexture(7/255, 8/255, 8/255, 0.98)
local line = window:CreateTexture(nil, "ARTWORK")
line:SetPoint("TOPLEFT"); line:SetPoint("TOPRIGHT"); line:SetHeight(2)
line:SetColorTexture(250/255, 204/255, 21/255, 1)
local logo = window:CreateTexture(nil, "ARTWORK")
logo:SetSize(42, 42); logo:SetPoint("TOPLEFT", 20, -14); logo:SetTexture(LOGO)
local function label(parent, font, x, y, width)
    local field = parent:CreateFontString(nil, "OVERLAY", font)
    field:SetPoint("TOPLEFT", x, y); field:SetWidth(width)
    field:SetJustifyH("LEFT"); field:SetJustifyV("TOP")
    field:SetTextColor(250/255, 250/255, 246/255)
    return field
end
label(window, "GameFontNormalLarge", 76, -24, 480):SetText("rbgs.io")
label(window, "GameFontHighlightSmall", 20, -72, 560):SetText(
    "Paste your match command from the companion into WoW chat before the battleground.\nAfter the match, use /reload or log out. Check uploads in the companion.")
local function button(name, caption, x, y, width, action)
    local control = CreateFrame("Button", name, window, "UIPanelButtonTemplate")
    control:SetSize(width, 26); control:SetPoint("TOPLEFT", x, y)
    control:SetText(caption); control:SetScript("OnClick", action)
    return control
end
button("RBGSProductClose", "X", 550, -20, 28, function() window:Hide() end)
button("RBGSProductReload", "Save / reload", 20, -380, 170, app.Reload)
button("RBGSProductRefresh", "Refresh view", 204, -380, 170, function() app.Refresh() end)
local historyOpen, historyIndex = false, 1
local historyButton = button("RBGSProductHistory", "Completed matches", 388, -380, 190, function()
    historyOpen = not historyOpen; historyIndex = 1; app.Refresh()
end)
local previous = button("RBGSHistoryPrevious", "Newer", 20, -110, 90, function()
    historyIndex = math.max(1, historyIndex-1); app.Refresh()
end)
local nextMatch = button("RBGSHistoryNext", "Older", 124, -110, 90, function()
    historyIndex = math.min(#app.CompletedMatches(), historyIndex+1); app.Refresh()
end)
local scroll = CreateFrame("ScrollFrame", "RBGSProductScroll", window, "UIPanelScrollFrameTemplate")
scroll:SetSize(532, 210); scroll:SetPoint("TOPLEFT", 20, -148)
local content = CreateFrame("Frame", nil, scroll)
content:SetSize(520, 228); scroll:SetScrollChild(content)
local details = label(content, "GameFontHighlightSmall", 0, 0, 516)
if type(UISpecialFrames) == "table" then table.insert(UISpecialFrames, "RBGSProductPanel") end
function app.Refresh()
    if not window:IsShown() then return end
    -- Prevent observed text from being interpreted as WoW color/texture/link markup.
    if historyOpen then
        local count = #app.CompletedMatches()
        historyIndex = math.max(1, math.min(historyIndex, count))
        previous:Show(); nextMatch:Show()
        previous:SetEnabled(historyIndex > 1); nextMatch:SetEnabled(historyIndex < count)
        historyButton:SetText("Recording status")
    else
        previous:Hide(); nextMatch:Hide(); historyButton:SetText("Completed matches")
    end
    details:SetText(((historyOpen and app.HistoryText(historyIndex) or app.Status()):gsub("|", "||")))
    content:SetHeight(math.max(210, details:GetStringHeight() + 12))
    scroll:SetVerticalScroll(0)
end
function app.ShowHistory()
    historyOpen = true; historyIndex = 1; app.ShowPanel()
end
function app.ShowPanel()
    window:SetScale(math.max(0.4, math.min(1, (UIParent:GetWidth()-40)/600, (UIParent:GetHeight()-40)/440)))
    window:Show(); app.Refresh()
end
window:SetScript("OnShow", app.Refresh)
window:Hide()

local launcher = CreateFrame("Button", "RBGSMinimapButton", Minimap or UIParent)
_G.RBGSProductLauncher = launcher -- Preserve the previous global for existing integrations.
launcher:SetSize(31, 31); launcher:SetFrameStrata("HIGH")
launcher:SetFrameLevel((Minimap and Minimap:GetFrameLevel() or 1) + 20)
launcher:EnableMouse(true); launcher:RegisterForClicks("LeftButtonUp"); launcher:RegisterForDrag("LeftButton")
launcher:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight")
local icon = launcher:CreateTexture(nil, "BACKGROUND")
icon:SetSize(20, 20); icon:SetPoint("CENTER", launcher, "CENTER", 0, 0)
icon:SetTexture(MINIMAP_LOGO, "CLAMP", "CLAMP", "LINEAR")
local border = launcher:CreateTexture(nil, "OVERLAY")
border:SetSize(53, 53); border:SetPoint("TOPLEFT")
border:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
local function settings()
    if type(RBGSSettings) ~= "table" then RBGSSettings = {} end
    local angle = RBGSSettings.minimapAngle
    if type(angle) ~= "number" or angle ~= angle or angle == math.huge or angle == -math.huge then angle = 315 end
    RBGSSettings.minimapAngle = angle % 360
    return RBGSSettings
end
local function position()
    if Minimap and launcher:GetParent() ~= Minimap then return end
    if not Minimap then launcher:SetPoint("TOPRIGHT", UIParent, "TOPRIGHT", -30, -130); return end
    local radians = math.rad(settings().minimapAngle)
    local radius = math.max(Minimap:GetWidth(), Minimap:GetHeight())/2 + 8
    launcher:ClearAllPoints()
    launcher:SetPoint("CENTER", Minimap, "CENTER", math.cos(radians)*radius, math.sin(radians)*radius)
end
launcher:RegisterEvent("PLAYER_LOGIN"); launcher:SetScript("OnEvent", position)
launcher:SetScript("OnClick", function(self)
    if self.dragging then return end
    if window:IsShown() then window:Hide() else app.ShowPanel() end
end)
launcher:SetScript("OnDragStart", function(self)
    if not Minimap or self:GetParent() ~= Minimap then return end
    self.dragging = true
    self:SetScript("OnUpdate", function()
        local x, y = GetCursorPosition()
        local cx, cy = Minimap:GetCenter()
        if not cx or not cy then return end
        local scale = Minimap:GetEffectiveScale()
        settings().minimapAngle = math.deg(math.atan2(y/scale-cy, x/scale-cx)) % 360
        position()
    end)
end)
launcher:SetScript("OnDragStop", function(self) self.dragging=false; self:SetScript("OnUpdate", nil) end)
launcher:SetScript("OnEnter", function(self)
    if not GameTooltip then return end
    GameTooltip:SetOwner(self, "ANCHOR_LEFT"); GameTooltip:SetText("rbgs.io")
    GameTooltip:AddLine("Left-click to open. Drag to move around the minimap.", 1, 1, 1); GameTooltip:Show()
end)
launcher:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
-- SavedVariables are available at login, so do not write settings during file load.
