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

- 纯色背景（推荐让 AI 用品红 `#FF00FF`）：用脚本去掉，输出 `<原名>_nobg.png`，和原图放在一起提交

  ```bat
  python tools\art\remove_bg.py art\source\tide_crystal\tide_crystal_v2_chatgpt.png
  ```

  它不只是把背景色变透明，还会把轮廓边缘混进去的背景色"减掉"（否则缩小后会有一圈紫边）。
  之后的图标、地面外观都用 `_nobg.png` 做输入
- 复杂背景：用去背景工具（如 ComfyUI 的抠图节点、rembg），再在 Krita/Photoshop 里手修边缘
- 判断标准：放到深色和浅色背景上都没有白边/彩边（第 ⑤ 步的预览会显示）

## ⑤ 规格化（脚本）

```bat
python tools\art\prepare_icon.py art\source\tide_crystal\tide_crystal_v2_chatgpt_nobg.png --name tide_crystal
```

（想加深色描边时加 `--outline 1`。`--key-color auto` 也能直接去纯色背景，算法同 remove_bg.py，但单独去背景更方便检查。）

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
| prompt_file / seed | 可选：有现成的就记，没有就写"未记录" |
| human_edits | "Krita 修边缘、加高光" |
| license_notes | 该工具服务条款对生成内容的商用/归属规定（链接 + 查阅日期） |
| status | `in_game` |

必须记的只有：用的是哪个工具、源图在哪、做了哪些处理。prompt 不强制记录（2026-10-11 决定）。
发布到创意工坊之前，查一次所用 AI 工具的服务条款（是否允许商用、生成内容归属、是否要求署名），记在 `license_notes`。

---

## 地面外观（单帧动画包）

物品掉在地上、建筑摆在世界里，显示的都是**动画包** `anim/<名字>.zip`，不是物品栏图标。
最简单的地面外观就是"一张图 = 一个单帧动画"，我们用自己的脚本生成，不需要 Spriter 和 Mod Tools：

```bat
python tools\art\make_anim.py item art\source\tide_crystal\tide_crystal_v2_chatgpt_nobg.png --name tide_crystal --height 135 --pivot 0.5,0.7 ^
    --compare "<DST安装目录>\data\anim\gems.zip:bluegem_idle" --compare "<DST安装目录>\data\anim\flint.zip:idle"

python tools\art\make_anim.py stages full=art\source\tide_crystal\tide_crystal_v1_chatgpt.png ^
    med=art\source\tide_crystal\tide_crystal_cluster_med.png low=art\source\tide_crystal\tide_crystal_cluster_low.png ^
    --name tide_crystal_cluster --height 300 --pivot 0.5,0.85 --compare "<DST安装目录>\data\anim\rock.zip:full"
```

`stages` 用于可开采物的破损阶段（结构和原版巨石 `rock.zip` 一样：一个 symbol 的第 0/1/2 帧，`full` / `med` / `low` 三个动画各引用一帧）。
**要求：各阶段图是同样大小、对齐好的画布**（底座在每张图里的位置一样）。第一张图决定缩放比例和原点，
后面几张用同样的比例和原点，所以底座在游戏里不会跳。每张图各自裁掉透明边，不浪费贴图。

### 破损阶段的图从哪来

1. 让 AI 在**完整图的基础上编辑**：上传完整图，要求同样构图、同样位置，只把晶体打断（一张"开裂、顶端断掉"，一张"只剩一小簇碎晶"）。
   原图存为 `<名字>_med_chatgpt.png` / `<名字>_low_chatgpt.png`；如果是纯色背景，先用 `remove_bg.py`
2. AI 改图时通常会把整体挪一点、缩放一点，用脚本把底座对齐到完整图：

   ```bat
   python tools\art\align_stages.py art\source\tide_crystal\tide_crystal_v1_chatgpt.png ^
       art\source\tide_crystal\tide_crystal_cluster_med_chatgpt.png art\source\tide_crystal\tide_crystal_cluster_low_chatgpt.png ^
       --out-names tide_crystal_cluster_med.png tide_crystal_cluster_low.png
   ```

   它只比较完整图底部 25%（石块底座），在 0.85–1.15 倍缩放和附近的平移里找重合最多的位置，输出和完整图同样大小的对齐图，
   并生成 `art\review\<完整图名>_onion.png`（红线是完整图轮廓，看各阶段底座是否落在红线底部）。
   潮蚀晶簇：med 缩放 0.975，low 缩放 0.925（low 的藤壶画大了约 10%，和搜索结果一致）
3. 用对齐后的图跑上面的 `make_anim.py stages`

- 输出 `mod\anim\tide_crystal.zip`：bank = build = symbol = `tide_crystal`，一个单帧动画 `idle`
- 输出 `art\review\tide_crystal_ground_preview.png`：和原版宝石、燧石**按同样比例**并排，红十字是实体原点，横线是地面
- `--height`：游戏里的高度（build 像素）。原版参考：蓝宝石 152×126，燧石堆 223×119，巨石 605×413
- `--pivot`：实体原点落在图上的位置（比例）。掉落物 0.5,0.5（宝石）~ 0.5,0.71（燧石堆）；建筑一般在底边附近
- 源图直接用 `art/source/` 里的原图（脚本自己裁边、缩放），同样的输入得到逐字节相同的 zip
- 脚本会把生成的 zip 读回来渲染一遍，和输入图比较误差

prefab 里这样用（`scripts/prefabs/tide_crystal.lua`）：

```lua
local assets = { Asset("ANIM", "anim/tide_crystal.zip") }
...
inst.AnimState:SetBank("tide_crystal")
inst.AnimState:SetBuild("tide_crystal")
inst.AnimState:PlayAnimation("idle")
```

`check_mod.py` 第 5 步会解析 `mod/anim/*.zip` 的结构，第 4 步会核对 prefab 里写的 bank / build / 动画名在包里真的存在
（写错名字在游戏里的表现是"物品隐形"，不会报错，所以要在这里拦住）。

**格式是怎么确认的**：`tools/art/kanim.py` 按游戏自带的 gems / flint / moondial / moondial_build 四个包实测格式；
`make_anim.py selftest <原版zip>` 把原版包读入再写出，四个包的 build.bin / anim.bin 都**逐字节相同**；
再用同一套坐标约定把原版宝石和燧石渲染出来，方向、拼接、图层顺序都正确。
格式细节（y 轴向下为正、贴图上下翻转存储、1 build 单位 = 1 贴图像素）写在 `kanim.py` 顶部。

当前的两个地面外观（2026-10-11）：

| prefab | 源图 | 尺寸 / 原点 | 状态 |
|---|---|---|---|
| `tide_crystal`（物品） | `tide_crystal_v2_chatgpt_nobg.png`（单块结晶） | 135 高，原点 0.5,0.7 | 待进游戏验证（第一版用 v1 晶簇图时已在游戏里显示正常） |
| `tide_crystal_cluster`（可开采） | `tide_crystal_v1_chatgpt.png` + ChatGPT 破损图 med / low（已对齐） | 300 高，原点 0.5,0.85，三个动画 full/med/low | 完整外观已在游戏里显示正常；破损阶段待验证 |

**颜色**：游戏按季节/昼夜给世界画面套颜色滤镜（见 API_NOTES「画面颜色」），地上的东西和物品栏图标颜色不同是正常的。
秋天白天青色会偏绿。如果以后想让某种颜色在各季节都更稳定，要在出图时考虑滤镜，不是改转换工具。

## 之后：多部件 / 多帧动画（祭坛等建筑）

`kanim.py` 的读写是通用的（多 symbol、多帧、多张贴图都能读写），但 `make_anim.py` 目前只会生成单帧单部件。
祭坛需要 idle / 激活 / 受击等多个状态时，有两条路，到时候按需要选：

1. **扩展 make_anim.py**：每个状态一组 PNG 帧（逐帧图），脚本把它们打包成多帧动画。适合 AI 出图 + 少量帧的简单动画
2. **Spriter + Don't Starve Mod Tools**：部件拆分 + 骨骼变换（位移/旋转/缩放），Mod Tools 的 autocompiler 把
   `exported/<名字>/<名字>.scml` 编译成 zip。适合需要平滑运动的动画；生成的 zip 也能用 `check_mod.py` 检查

无论哪条路：AI 擅长出同一风格的**部件草图和单帧图**；多帧之间保持一致、部件拆分、枢轴点需要人来把关。
