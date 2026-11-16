-- Neon Dial: in-game control panel + radio "physics" for the Neon Dial FM station.
-- The station itself comes from RadioExt (radioExt/radios/NeonDial). The companion (NeonDial.exe, started
-- with the game) exchanges small text files with this mod: status.txt (companion -> here), command.txt (here -> companion).
-- Everything is wrapped in pcall so a problem here can never break the game.

local STATION = "Neon Dial FM"          -- RadioExt station name = displayName in metadata.json
local SETTINGS_FILE = "settings.txt"

local cfg = { physics = true, near = 4.0, far = 45.0, cabin = 0.18, dedupe = true, volfix = true }
local ui = { open = false, status = {}, log = {}, connected = false, lastRead = 0, tick = 0 }
local lastVol = {}

local MODES = { "system", "standalone", "apple-standalone" }
local MODE_LABELS = { "Music app (Apple Music / Spotify must be open)", "Standalone Spotify (no app, Premium)", "Standalone Apple Music (no app)" }
local TEXTURES = { "off", "radio", "lofi", "warm" }
local TEXTURE_LABELS = { "Clean", "Radio (band-limited, light static)", "Lo-fi", "Warm tape" }

---------------------------------------------------------------- files
local function readAll(path)
    local f = io.open(path, "r")
    if not f then return nil end
    local t = f:read("*a")
    f:close()
    return t
end

local function saveSettings()
    local f = io.open(SETTINGS_FILE, "w")
    if not f then return end
    f:write(string.format("physics=%d\nnear=%.2f\nfar=%.2f\ncabin=%.2f\ndedupe=%d\nvolfix=%d\n",
        cfg.physics and 1 or 0, cfg.near, cfg.far, cfg.cabin, cfg.dedupe and 1 or 0, cfg.volfix and 1 or 0))
    f:close()
end

local function loadSettings()
    local t = readAll(SETTINGS_FILE)
    if not t then return end
    for k, v in t:gmatch("(%w+)=([%-%d%.]+)") do
        v = tonumber(v)
        if k == "physics" then cfg.physics = v == 1
        elseif k == "dedupe" then cfg.dedupe = v == 1
        elseif k == "volfix" then cfg.volfix = v == 1
        elseif cfg[k] ~= nil and v then cfg[k] = v end
    end
end

local function send(cmd)
    local f = io.open("command.txt", "a")
    if f then f:write(cmd .. "\n"); f:close() end
end

local function readStatus()
    local t = readAll("status.txt")
    if not t then ui.connected = false; return end
    local kv, log = {}, {}
    for line in t:gmatch("[^\r\n]+") do
        local k, v = line:match("^([%w_]+)=(.*)$")
        if k then
            if k == "log" then log[#log + 1] = v else kv[k] = v end
        end
    end
    ui.status, ui.log = kv, log
    ui.connected = (os.time() - (tonumber(kv.ts) or 0)) < 10
end

---------------------------------------------------------------- game helpers
local function setting(name)
    local ok, v = pcall(function() return Game.GetSettingsSystem():GetVar("/audio/volume", name):GetValue() end)
    if ok and type(v) == "number" then return v end
    return 100
end

local function radioExt()
    local ok, rx = pcall(GetMod, "radioExt")
    if ok then return rx end
    return nil
end

local function dist(a, b)
    local dx, dy, dz = a.x - b.x, a.y - b.y, a.z - b.z
    return math.sqrt(dx * dx + dy * dy + dz * dz)
end

local function smooth(x)
    if x < 0 then x = 0 elseif x > 1 then x = 1 end
    return x * x * (3 - 2 * x)
end

---------------------------------------------------------------- radio physics / volume fixes
-- RadioExt does not apply the "Radioport volume" slider to radios placed in the world, and keeps a radio box playing at full
-- strength inside a car. Here we apply the slider, distance fall-off and an in-car muffling factor, and silence a radio box
-- that would otherwise play the same station twice (car + box) with an echo.
local function updateVolumes()
    local rx = radioExt()
    local mgr = rx and rx.radioManager
    if not mgr or not mgr.managerP then return end
    local station = mgr.getRadioByName and mgr:getRadioByName(STATION)
    if not station then return end

    local player = Game.GetPlayer()
    if not player then return end
    local ppos = player:GetWorldPosition()
    local mounted = player:GetMountedVehicle() ~= nil
    local slider = setting("RadioportVolume") / 100
    local ownOnMain = station.channels and station.channels[-1] == true

    for ch, obj in pairs(mgr.managerP.radioObjects or {}) do
        if obj.radio == station then
            local base = (station.volume or 1.0) * 0.7 * 0.4        -- same base RadioExt uses for world radios
            local g = 1.0
            if cfg.volfix then g = g * slider end
            if cfg.physics and obj.handle and IsDefined(obj.handle) then
                local d = dist(ppos, obj.handle:GetWorldPosition())
                g = g * (1.0 - smooth((d - cfg.near) / math.max(1.0, cfg.far - cfg.near)))
            end
            if mounted and cfg.physics then g = g * cfg.cabin end
            if cfg.dedupe and ownOnMain then g = 0.0 end            -- car/pocket radio already plays this station
            local vol = base * g
            if not lastVol[ch] or math.abs(lastVol[ch] - vol) > 0.002 then
                lastVol[ch] = vol
                RadioExt.SetVolume(ch, vol)
            end
        else
            lastVol[ch] = nil
        end
    end
end

---------------------------------------------------------------- now playing in the game's radio UI
-- RadioExt shows the stream address as the "track name". After it has drawn that text we replace it with the real song
-- (Artist - Title), both in the radio select screen and in the pop-up when switching stations.
local pending = { popup = nil, notif = nil }
local popupCtrl = nil
local shownText = nil

local function nowText()
    local t = ui.status.title or ""
    if t == "" then return nil end
    local a = ui.status.artist or ""
    if a ~= "" then return a .. " - " .. t end
    return t
end

local function stationIsOurs()
    local rx = radioExt()
    local mv = rx and rx.radioManager and rx.radioManager.managerV
    if not mv or not mv.getActiveStationData then return false end
    local active = mv:getActiveStationData()
    return active ~= nil and active.station == STATION
end

local function applyPopup(ctrl, text)
    if not ctrl or not text then return false end
    local ok = pcall(function()
        ctrl.trackName:SetText(text)
        ctrl.trackName:SetVisible(true)
    end)
    return ok
end

local function applyNotif(ctrl, text)
    if not ctrl or not text then return end
    pcall(function() inkTextRef.SetText(ctrl.subText, text) end)
end

local function updateNowPlaying()
    local text = nowText()
    if pending.popup or pending.notif then
        if stationIsOurs() and text then
            if pending.popup then
                popupCtrl = pending.popup
                applyPopup(popupCtrl, text)
            end
            if pending.notif then applyNotif(pending.notif, text) end
            shownText = text
        end
        pending.popup, pending.notif = nil, nil
        return
    end
    -- song changed while the select screen is open
    if popupCtrl and text and text ~= shownText and stationIsOurs() then
        if applyPopup(popupCtrl, text) then shownText = text else popupCtrl = nil end
    end
end

---------------------------------------------------------------- UI
local function combo(label, items, labels, current)
    local idx = 0
    for i, v in ipairs(items) do if v == current then idx = i - 1 end end
    local newIdx, changed = ImGui.Combo(label, idx, labels, #labels)
    if changed then return items[newIdx + 1], true end
    return current, false
end

local function draw()
    if not ImGui.Begin("Neon Dial", ImGuiWindowFlags.AlwaysAutoResize) then ImGui.End(); return end
    local s = ui.status
    if not ui.connected then
        ImGui.TextWrapped("The Neon Dial helper isn't running. It starts with the game (NeonDial.exe); check red4ext/logs if it doesn't.")
    else
        local mode = s.mode or "system"
        ImGui.Text("Mode")
        local newMode, ch = combo("##nd_mode", MODES, MODE_LABELS, mode)
        if ch then send("mode=" .. newMode) end
        ImGui.Separator()
        ImGui.Text((s.tuned == "1") and "Tuned in" or "Idle")
        if s.title and s.title ~= "" then ImGui.Text("Now: " .. s.title .. " - " .. (s.artist or "")) end
        if s.path then ImGui.Text("Audio path: " .. s.path) end
        if s.note and s.note ~= "" then ImGui.TextWrapped(s.note) end
        if ImGui.Button("Prev") then send("action=prev") end
        ImGui.SameLine()
        if ImGui.Button("Next") then send("action=next") end
        if mode == "apple-standalone" then
            ImGui.SameLine()
            if ImGui.Button("Apple sign-in window") then send("window=show") end
            ImGui.SameLine()
            if ImGui.Button("Hide window") then send("window=hide") end
        end
        ImGui.Separator()
        ImGui.Text("Sound texture")
        local tex, tch = combo("##nd_tex", TEXTURES, TEXTURE_LABELS, s.texture or "off")
        if tch then send("texture=" .. tex) end
    end
    if ui.connected then
        ImGui.Separator()
        if ui.confirmForget then
            if ImGui.Button("Yes, sign out and erase saved logins") then send("forget=all"); ui.confirmForget = false end
            ImGui.SameLine()
            if ImGui.Button("Cancel") then ui.confirmForget = false end
        else
            if ImGui.Button("Sign out and erase saved logins") then ui.confirmForget = true end
        end
    end
    ImGui.Separator()
    ImGui.Text("Radio physics")
    local v, changed = ImGui.Checkbox("Distance fall-off and in-car muffling for radio boxes", cfg.physics)
    if changed then cfg.physics = v; saveSettings() end
    v, changed = ImGui.Checkbox("Apply the Radioport volume setting to radio boxes", cfg.volfix)
    if changed then cfg.volfix = v; saveSettings() end
    v, changed = ImGui.Checkbox("Mute a radio box when the car already plays this station", cfg.dedupe)
    if changed then cfg.dedupe = v; saveSettings() end
    if cfg.physics then
        local nv, used = ImGui.SliderFloat("Full volume within (m)", cfg.near, 1.0, 20.0, "%.0f")
        if used then cfg.near = nv; saveSettings() end
        nv, used = ImGui.SliderFloat("Silent beyond (m)", cfg.far, 10.0, 120.0, "%.0f")
        if used then cfg.far = nv; saveSettings() end
        nv, used = ImGui.SliderFloat("Volume inside a car", cfg.cabin, 0.0, 1.0, "%.2f")
        if used then cfg.cabin = nv; saveSettings() end
    end
    if #ui.log > 0 then
        ImGui.Separator()
        ImGui.Text("Activity")
        for i = math.max(1, #ui.log - 7), #ui.log do ImGui.TextWrapped(ui.log[i]) end
    end
    ImGui.End()
end

---------------------------------------------------------------- events
registerForEvent("onInit", function()
    loadSettings()
    pcall(function()
        ObserveAfter("VehicleRadioPopupGameController", "SetTrackName", function(this) pending.popup = this end)
        ObserveAfter("VehicleSummonWidgetGameController", "TryShowVehicleRadioNotification", function(this) pending.notif = this end)
        ObserveAfter("VehicleRadioPopupGameController", "OnUninitialize", function() popupCtrl = nil; shownText = nil end)
    end)
    print("[NeonDial] ready. Open the CET overlay to control it; station: " .. STATION)
end)

registerForEvent("onOverlayOpen", function() ui.open = true end)
registerForEvent("onOverlayClose", function() ui.open = false end)

registerForEvent("onUpdate", function(dt)
    ui.tick = ui.tick + dt
    if ui.tick < 0.1 then return end
    ui.tick = 0
    pcall(updateVolumes)
    pcall(updateNowPlaying)
    ui.lastRead = ui.lastRead + 1
    if ui.lastRead >= 10 then ui.lastRead = 0; pcall(readStatus) end
end)

registerForEvent("onDraw", function()
    if not ui.open then return end
    local ok, err = pcall(draw)
    if not ok then
        print("[NeonDial] UI error: " .. tostring(err))
        pcall(ImGui.End)
    end
end)

registerHotkey("neondial_next", "Neon Dial: next track", function() send("action=next") end)
registerHotkey("neondial_prev", "Neon Dial: previous track", function() send("action=prev") end)
registerHotkey("neondial_window", "Neon Dial: show Apple Music sign-in window", function() send("window=show") end)
