local addonName, app = ...
local button, board, leave, hiddenLeave, saving, bypassId, preparingId
local elapsed, reloadElapsed = 0, nil
local pending, reopenElapsed, worldReady, loadAttempted
local hooked, refreshing = {}, false
local function target()
    if PVPMatchResults and PVPMatchResults.leaveButton then return PVPMatchResults, PVPMatchResults.leaveButton end
    if WorldStateScoreFrame and WorldStateScoreFrameLeaveButton then return WorldStateScoreFrame, WorldStateScoreFrameLeaveButton end
end
local function timestamp()
    local values = app.Adapter.Call(GetServerTime)
    local value = values and values[1]
    if app.Store.Integer(value) then return value end
end
local function restoreLeave()
    if hiddenLeave and pcall(hiddenLeave.Show, hiddenLeave) then hiddenLeave = nil end
end
local function showOriginal()
    restoreLeave()
    if button then button:Hide() end
end
function app.ResultsReloadFailed()
    if type(RBGSSettings) == "table" then RBGSSettings.reopenResults = nil end
    bypassId, preparingId, reloadElapsed, saving = preparingId, nil, nil, false
    showOriginal()
end
function app.PrepareResultsReload()
    local visible, ready, _, record = app.ResultSaveState()
    if not visible or not ready or not record then return end
    preparingId, reloadElapsed = record.captureId, 0
    local now = timestamp()
    if not now then return end
    if type(RBGSSettings) ~= "table" then RBGSSettings = {} end
    -- UI intent only, separate from immutable match evidence and without any command/code.
    RBGSSettings.reopenResults = {schema=1, captureId=record.captureId, revision=record.captureRevision, requestedAt=now}
end
local function hook(frame, event)
    if not frame or type(frame.HookScript) ~= "function" then return end
    hooked[frame] = hooked[frame] or {}
    if hooked[frame][event] then return end
    frame:HookScript(event, function() app.RefreshResultsButton() end)
    hooked[frame][event] = true
end
local function refresh()
    local parent, anchor = target()
    hook(parent, "OnShow"); hook(parent, "OnHide"); hook(anchor, "OnShow")
    local visible, ready, _, record = app.ResultSaveState()
    local combat = app.Adapter.Call(InCombatLockdown)
    if not visible or not parent or not parent:IsShown() or not combat or combat[1]
        or record and record.captureId == bypassId then showOriginal(); return end
    if anchor ~= hiddenLeave and not anchor:IsShown() then showOriginal(); return end
    if not button then
        board, leave = parent, anchor
        button = CreateFrame("Button", "RBGSScoreboardSaveResults", board, "UIPanelButtonTemplate")
        button:SetSize(220, math.max(18, leave:GetHeight()))
        button:SetPoint("CENTER", leave, "CENTER", 0, 0)
        button:SetScript("OnClick", function()
            if saving then return end
            saving = app.SaveMatchResults() == true
            app.RefreshResultsButton()
        end)
        button:SetScript("OnEnter", function(self)
            if not GameTooltip then return end
            local _, _, hint = app.ResultSaveState()
            GameTooltip:SetOwner(self, "ANCHOR_TOP")
            GameTooltip:SetText("rbgs.io: Save results")
            GameTooltip:AddLine(hint or "Save your completed RBGS recording with /reload.", 1, 1, 1, true)
            GameTooltip:Show()
        end)
        button:SetScript("OnLeave", function() if GameTooltip then GameTooltip:Hide() end end)
    end
    if board ~= parent or leave ~= anchor then showOriginal(); return end
    button:SetText(saving and "rbgs.io: Saving results..." or ready and "rbgs.io: Save results" or "rbgs.io: Reading results...")
    button:SetEnabled(ready and not saving)
    -- Preserve the native exit's position, text and click handler for after the reload.
    button:Show()
    hiddenLeave = anchor
    anchor:Hide()
end
function app.RefreshResultsButton()
    if refreshing then return end
    refreshing = true
    local ok = pcall(refresh)
    if not ok then pcall(showOriginal) end
    refreshing = false
end
local function restoredRecord()
    if type(pending) ~= "table" or pending.schema ~= 1 or type(pending.captureId) ~= "string"
        or #pending.captureId ~= 36 or not app.Store.Integer(pending.revision)
        or not app.Store.Integer(pending.requestedAt) or not app.store or app.store.error then return end
    local now = timestamp()
    if not now or now < pending.requestedAt or now - pending.requestedAt > 120 then return end
    for _, record in ipairs(app.store.root.captures) do
        local capture = record.capture
        if record.captureId == pending.captureId and record.captureRevision == pending.revision
            and capture.state == "COMPLETE" and capture.stage == "COMPLETE" and capture.map then
            return record
        end
    end
end
local function reopen(delta)
    if not worldReady or not pending then return end
    reopenElapsed = reopenElapsed + delta
    local record = restoredRecord()
    if not record or reopenElapsed > 15 then pending = nil; return end
    if not app.client or record.client.product ~= app.client.product then pending = nil; return end
    local identity = app.Adapter.Identity()
    if not identity then return end
    local character = record.observedCharacter
    if character.name ~= identity.name or character.realm ~= identity.realm or character.guid ~= identity.guid then pending = nil; return end
    local inBG, map = app.Adapter.Context()
    local winner, readable = app.Adapter.Winner()
    if inBG and (map.gameMapId ~= record.capture.map.gameMapId or map.profile ~= record.capture.map.profile
        or readable and winner ~= nil and tostring(winner) ~= record.capture.outcome.winningObservedTeamKey) then
        pending = nil; return
    end
    local combat = app.Adapter.Call(InCombatLockdown)
    if inBG ~= true or not readable or winner == nil or not combat or combat[1] then return end
    local roster = app.Adapter.Roster()
    if not roster or #roster == 0 then return end
    local parent = target()
    if not parent and not loadAttempted and app.client.product ~= "wow_anniversary" then
        loadAttempted = true
        app.Adapter.Call(UIParentLoadAddOn, "Blizzard_PVPMatch")
        parent = target()
    end
    if not parent then return end
    showOriginal()
    if not parent:IsShown() then
        if type(parent.BeginShow) == "function" then parent:BeginShow()
        elseif type(ShowUIPanel) == "function" then ShowUIPanel(parent)
        else parent:Show() end
    end
    if parent:IsShown() then
        pending = nil
        app.Message("Results saved. You can now leave the match. Check uploads in the companion.")
    end
end
local watcher = CreateFrame("Frame")
watcher:RegisterEvent("ADDON_LOADED"); watcher:RegisterEvent("PLAYER_ENTERING_WORLD")
watcher:SetScript("OnEvent", function(_, event, first, isReloadingUI)
    if event == "ADDON_LOADED" and first == addonName then
        if type(RBGSSettings) == "table" then
            pending = RBGSSettings.reopenResults
            RBGSSettings.reopenResults = nil -- Consume before any attempt; never reopen on a later login.
        end
    elseif event == "PLAYER_ENTERING_WORLD" and pending then
        if first == true or isReloadingUI ~= true then pending = nil; return end
        worldReady, reopenElapsed = true, 0
        app.Adapter.Request()
    end
    app.RefreshResultsButton()
end)
watcher:SetScript("OnUpdate", function(_, delta)
    if reloadElapsed then
        reloadElapsed = reloadElapsed + delta
        if reloadElapsed >= 10 then
            app.ResultsReloadFailed()
            app.Message("Reload did not finish. Use /reload manually to save, then leave the match.")
        end
    end
    elapsed = elapsed + delta
    if elapsed < 0.5 then return end
    local step = elapsed
    elapsed = 0
    if not pcall(reopen, step) then pending = nil end
    app.RefreshResultsButton()
end)
