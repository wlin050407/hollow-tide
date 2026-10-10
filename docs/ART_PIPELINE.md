# AI 美术管线：第一个原创图标（潮蚀结晶）

> 核心认识：**AI 生成的是"候选图"，不是"资产"**。一张图要经过筛选、清理、规格化、格式转换、进游戏验证，
> 才算资产。这条管线的目标是：除了"挑哪张"和"像不像我们的游戏"这两个判断，其余步骤都可以脚本化、可重复。

```
 ① 风格基准 → ② 批量生成 → ③ 人工筛选 → ④ 去背景 → ⑤ 规格化(脚本) → ⑥ PNG→TEX/XML → ⑦ 接入代码 → ⑧ 进游戏验证 → ⑨ 记录来源
     人          AI            人          脚本/工具       脚本           工具             人/AI         人              脚本+人
```

## ① 风格基准（一次性，成员 C 负责）

在 `art/STYLE.md`（第一周建立）里用**文字**写清楚我们要的视觉特征，作为所有 prompt 的共同前缀：

- 粗、略带抖动的深褐/近黑色墨线轮廓；轮廓在 64px 下仍清晰可辨
- 低饱和、偏冷偏暗的配色；高光少而集中
- 手绘质感，轻微的纸张/笔刷纹理；不要 3D 渲染感、不要光滑渐变、不要写实
- 造型略夸张、不对称，带一点"暗黑童话"的怪异感
- 光源统一来自左上方

**不要**把原版贴图直接喂给模型做图生图或风格迁移：容易产出近似复制品，也违背"所有设计保持原创"的目标。
可以用**我们自己审核通过的图**做后续的风格参考，逐步形成 Hollow Lantern 自己的视觉语言。

## ② 批量生成

`art/prompts/tide_crystal_icon.md` 里有第一版 prompt 模板。要点：

- 1024×1024，单个物体、居中、3/4 俯视角，四周留足空白
- **纯色背景**，选一个和物体颜色差别大的颜色（青绿色结晶 → 品红 `#FF00FF` 背景），方便脚本抠图
- 不要文字、不要地面阴影、不要边框
- 一次生成 8–16 张，原始文件放 `art/_inbox/`（不进 Git）

如果你们本地跑 ComfyUI 之类的工具，可以把"生成 → 去背景"做成一个固定工作流，每次只换 prompt 和种子。

## ③ 人工筛选（不可省略）

把候选图缩小到 64px 再看（第 ⑤ 步的预览图就是干这个的）。检查：

- [ ] 64px 下一眼能认出是什么、和原版的蓝宝石/月岩等不会混淆
- [ ] 轮廓粗细、配色和 STYLE.md 一致
- [ ] 没有 AI 常见瑕疵（多余碎片、糊边、不对称的错误、奇怪的纹理文字）
- [ ] 不像任何现有作品的标志性设计

选中的 1–2 张移到 `art/source/tide_crystal/`，同时保存 prompt 和种子。

## ④ 去背景

- 纯色背景：直接交给第 ⑤ 步的 `--key-color auto`
- 复杂背景：用去背景工具（如 ComfyUI 的抠图节点、rembg），再在 Krita/Photoshop 里手修边缘
- 判断标准：放到深色和浅色背景上都没有白边/彩边（第 ⑤ 步的预览会显示）

## ⑤ 规格化（脚本）

```bat
python tools\art\prepare_icon.py art\source\tide_crystal\tide_crystal_v1_chatgpt.png --name tide_crystal
```

（源图是纯色背景时加 `--key-color auto`；想加深色描边时加 `--outline 1`。）

输出：
- `art\icons\tide_crystal.png`：64×64 透明 PNG（裁边、等比缩放、居中、预乘 alpha 缩放避免白边）
- `art\review\tide_crystal_preview.png`：深色格子 / 浅色背景 / 1×2×4 倍放大对比，**给人审查用**

脚本会自检：边缘是否透明、主体占比是否合适、是否有白底残留的光晕。`--name` 必须等于 prefab 名。

## ⑥ PNG → TEX + XML（脚本）

```bat
python tools\art\png2tex.py art\icons\tide_crystal.png
```

输出 `mod\images\inventoryimages\tide_crystal.tex` 和 `tide_crystal.xml`，并用独立解码器读回做一次比对。

`png2tex.py` 是我们自己的转换器（纯 Python，不需要安装 Mod Tools），格式已对照游戏自带贴图验证过：
- 文件头字段、DXT5、完整 mipmap 链、预乘 alpha、**上下翻转存储**、UV 半像素内缩，都与原版 `inventoryimages*.tex` 一致
- 验证方法：把原版火炬图标正过来、用本工具重新编码，得到的数据与原版存储的数据几乎逐像素一致（颜色误差 0.0、alpha 误差 0.4）；不翻转时误差很大
- 已在游戏里验证（2026-10-11，潮蚀结晶在物品栏中显示正常）

备用方案（如果游戏里显示不对）：Steam 工具 **Don't Starve Mod Tools** 的 autocompiler / `png.exe`，或社区工具 ktools 的 `ktech`
（`ktech tide_crystal.png tide_crystal.tex`）。两者的默认行为与 `png2tex.py` 相同。

## ⑦ 接入代码

`mod/modmain.lua`：

```lua
Assets =
{
    Asset("ATLAS", "images/inventoryimages/tide_crystal.xml"),
    Asset("IMAGE", "images/inventoryimages/tide_crystal.tex"),
}

-- 在 modmain 顶层注册（早于任何图标查询），并传 resolve 后的路径（见 API_NOTES.md「物品栏图标」）
RegisterInventoryItemAtlas(GLOBAL.resolvefilepath("images/inventoryimages/tide_crystal.xml"), "tide_crystal.tex")
```

`mod/scripts/prefabs/tide_crystal.lua`：删掉 `inst.components.inventoryitem.imagename = "bluegem"` 这一行
（不设 imagename 时默认就是 `tide_crystal.tex`，会在刚注册的图集里找到）。
如果以后某个物品的图标名和 prefab 名不同，必须同时设置 `imagename` 和 `atlasname`：设了 imagename 后客户端拿到的是 hash，查不到按字符串注册的图集。

注意 `resolvefilepath` 在找不到文件时会直接让游戏崩溃 —— 所以先跑 `check_mod.py` 确认文件都在。

潮蚀结晶已按本步骤接入（2026-10-11），游戏内显示正常。

## ⑧ 进游戏验证

- [ ] 物品栏格子里显示正常，和旁边的原版图标放在一起不突兀（**最重要的主观检查，截图存档**）
- [ ] 拖在鼠标上、放进箱子、放进背包都正常
- [ ] 鼠标悬停名称正确
- [ ] 带洞穴的世界里（你是客户端）显示正常
- [ ] `client_log.txt` 没有贴图相关的报错

## ⑨ 记录来源

在 `art/provenance/asset_log.csv` 里加一行：

| 字段 | 示例 |
|---|---|
| asset_id | `icon_tide_crystal_v1` |
| game_file | `mod/images/inventoryimages/tide_crystal.tex` |
| source_file | `art/source/tide_crystal/tide_crystal_v1.png` |
| tool / model_or_version | 生成工具名 / 模型名和版本 |
| prompt_file / seed | `art/prompts/tide_crystal_icon.md` / 种子 |
| human_edits | "Krita 修边缘、加高光" |
| license_notes | 该工具服务条款对生成内容的商用/归属规定（链接 + 查阅日期） |
| status | `in_game` |

每个使用的 AI 工具，第一次用之前都要查一次它的服务条款（是否允许商用、生成内容归属、是否要求署名），记在 `license_notes`。

---

## 之后：动画资产（第 2 周开始）

DST 的动画是 Spriter 骨骼/切片动画：一个 **build**（贴图部件，称为 symbol）+ 一个 **bank**（动画数据），
Mod Tools 把 `exported/<名字>/<名字>.scml` 编译成 `anim/<名字>.zip`。这意味着：

- AI 擅长：同一风格下的**部件草图**（结晶的底座、发光核心、碎片）、特效序列的参考
- AI 不擅长：多帧之间保持一致、多朝向一致、正确的部件拆分和枢轴点 —— 这些需要人在 Spriter 里完成
- 第一阶段只做"刚体部件 + 变换动画"（位移/旋转/缩放/透明度），不做逐帧手绘动画
- 第 2 周的验收门槛：一个原创的、有 ≥3 个状态（idle / 激活 / 受击）的祭坛动画在游戏里正常播放
