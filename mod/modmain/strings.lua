-- modmain/strings.lua（由 modmain.lua 通过 modimport 载入，运行在 Mod 沙盒）
--
-- 所有玩家可见文本集中在这里，中英文并排，方便翻译和审查。
-- 语言选择：Mod 设置 "language" = auto / en / zh。
--   auto 时读取本机游戏语言 LOC.GetLocaleCode()：zh(简体) / zht(繁体) / zhr(WeGame) 都归为中文。
-- 注意：物品名称在每台机器本地显示；但"检查"时角色说的台词是服务器生成后发给客户端的，
-- 所以台词语言跟随服务器（带洞穴的世界里，服务器语言 = 创建世界时的服务器语言设置）。

local _G = GLOBAL
local STRINGS = _G.STRINGS

local function resolve_language()
    local setting = GetModConfigData("language")
    if setting == "zh" or setting == "en" then
        return setting
    end
    local code = _G.LOC.GetLocaleCode()
    if code == "zh" or code == "zht" or code == "zhr" then
        return "zh"
    end
    return "en"
end

local TEXT =
{
    en =
    {
        NAMES =
        {
            TIDE_CRYSTAL = "Tide Crystal",
            TIDE_CRYSTAL_CLUSTER = "Tide Crystal Cluster",
            TIDE_ALTAR = "Tide Altar",
        },
        RECIPE_DESC =
        {
            TIDE_ALTAR = "Borrow the tide from the deep.",
        },
        -- 动作文字：STRINGS.ACTIONS.ACTIVATE.<键>，键由 prefab 的 GetActivateVerb 返回
        ACTIVATE =
        {
            TIDE_ALTAR = "Call the Tide",
        },
        DESCRIBE =
        {
            TIDE_CRYSTAL = "It hums like a shell held to the ear.",
            TIDE_CRYSTAL_CLUSTER = "The tide left this behind. It's still humming.",
            TIDE_ALTAR =
            {
                GENERIC = "Something far below is listening.",
                ACTIVE = "The tide is answering!",
                COOLDOWN = "It needs to catch its breath.",
            },
        },
    },
    zh =
    {
        NAMES =
        {
            TIDE_CRYSTAL = "潮蚀结晶",
            TIDE_CRYSTAL_CLUSTER = "潮蚀晶簇",
            TIDE_ALTAR = "深潮祭坛",
        },
        RECIPE_DESC =
        {
            TIDE_ALTAR = "向深海借一次潮水。",
        },
        ACTIVATE =
        {
            TIDE_ALTAR = "唤潮",
        },
        DESCRIBE =
        {
            TIDE_CRYSTAL = "贴近耳边，能听见很远很远的潮声。",
            TIDE_CRYSTAL_CLUSTER = "潮水退去后留下的，还在嗡嗡作响。",
            TIDE_ALTAR =
            {
                GENERIC = "海螺深处，有什么东西在听。",
                ACTIVE = "潮水在回应它！",
                COOLDOWN = "它得先喘口气。",
            },
        },
    },
}

local lang = resolve_language()
local text = TEXT[lang]

for key, value in pairs(text.NAMES) do
    STRINGS.NAMES[key] = value
end

-- GENERIC 是所有角色的默认台词；以后可以按角色单独覆盖（STRINGS.CHARACTERS.WILLOW.DESCRIBE ...）
-- 值是表时，键对应 inspectable.getstatus 返回的状态（GENERIC / ACTIVE / ...，原版 moondial 同样写法）
for key, value in pairs(text.DESCRIBE) do
    STRINGS.CHARACTERS.GENERIC.DESCRIBE[key] = value
end

for key, value in pairs(text.RECIPE_DESC) do
    STRINGS.RECIPE_DESC[key] = value
end

for key, value in pairs(text.ACTIVATE) do
    STRINGS.ACTIONS.ACTIVATE[key] = value
end

require("hollowtide/log").Debug("strings loaded, language=%s", lang)
