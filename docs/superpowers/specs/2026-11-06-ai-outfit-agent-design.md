# 本地 AI 穿搭助手 · 设计文档

- 日期：2026-11-06
- 状态：已与用户逐段确认，待实现
- 代号：Outfit

---

## 1. 背景

用户希望在自己笔记本上装一个穿搭助手：告诉它身高体重、一张身体照片、衣橱里有哪些衣服和饰品，它按当天场合与天气给出穿搭方案，并生成"你穿着这套"的效果图。此外它要能判断一件新衣服值不值得买。

这件事在 2026 年已经可做，难点不在"能不能生成一张图"，而在三件事：

1. 衣服入库的标签质量——标签错了，后面全错；
2. 出图不能把人脸和衣服改坏——用户对"这不像我"零容忍；
3. 花出去的钱要能看见——每张合成图都是真金白银。

设计围绕这三件事展开。

---

## 2. 目标

| 编号 | 目标 | 可验证标准 |
|---|---|---|
| G1 | 单件衣服拍照入库 | 从拍照到确认完成 ≤ 20 秒，人工只需点两下 |
| G2 | 早上出方案 | 说一句话到看见 3 套方案 ≤ 15 秒（不含出图） |
| G3 | 看到自己穿上的效果 | 至少 1 套出图成功；失败时降级为搭配板而不是报错 |
| G4 | 买前判断 | 拍一件新衣服，给出"买/不买/看价格"及能和衣橱里哪几件搭 |
| G5 | 隐私 | 原始照片不出本机；无账号、无遥测 |

---

## 3. 非目标（这一版明确不做）

- 公网访问、多用户、账号体系
- 行程级打包（下周出差该带什么）
- 购物链接、比价、尺码推荐到具体品牌
- 视频、动图、多角度旋转
- 社交分享、穿搭社区
- 从电商商品页批量抓图入库（v2 候选）
- 3D 体型重建、精确尺码换算

---

## 4. 三个影响设计的前提判断

### 4.1 裸照不是好输入

用户最初提出提供裸照。设计上不采用，改为**深色贴身背心 + 短裤、白墙前、正对光、全身入镜**一张，理由：

- 主流图像模型与试穿服务对裸露图像有安全过滤，会直接拒图或糊化处理，等于白拍；
- 贴身衣物反而帮助模型判断肩线、腰线、腿长比例，出图更准；
- 一旦泄露，代价远大于穿衣照，且没有技术收益换来这个代价。

采集规范写入"我的"页面提示：白墙、正对自然光、手机与胸同高、脚拍到脚背、不要自拍角度、不要滤镜。

比多拍十张更有用的是这几个数字：肩宽、胸围、腰围、臀围、裤长（或直接量一件最合身的衣服）。

### 4.2 出图走云端，且默认选国内可直连的模型

用户已确认走云 API。默认供应商选择**国内可直连的多图参考编辑模型**（如阿里云百炼 Qwen-Image-Edit、火山引擎 Seedream 系列），因为 Gemini 类服务在中国大陆需要额外网络条件，把一个需要代理的依赖放进"每天早上用"的链路里是脆弱设计。

Gemini 2.5 Flash Image 作为可选适配器保留——它的多图合成能力更强。供应商通过配置切换，不写死在代码里。

不选传统 VTON（IDM-VTON / OOTDiffusion）的原因：一次只能换一件，"内搭＋外套＋裤＋鞋＋包"要串四五轮，每轮掉一次画质，最后人体比例会崩。

### 4.3 手机浏览器 + 局域网

用户已确认要手机拍、手机看。笔记本起本地服务，手机连同一 Wi-Fi 扫码访问。代价是出门在外用不了——这个代价换来"照片不出家门"，接受。

---

## 5. 架构

### 5.1 技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| 运行时 | Python 3.10+（本机已是 3.10.11） | 抠图、图像处理、尺寸计算全在 Python 生态 |
| 服务 | FastAPI + uvicorn | 自带 OpenAPI、异步、静态文件托管够用 |
| 数据 | SQLite（WAL）+ 本地图片目录 | 单用户、几百件衣服；备份 = 复制一个目录 |
| 数据访问 | SQLModel（SQLAlchemy 2 + Pydantic） | 表结构与 API 模型同一份定义，少一层翻译 |
| 前端 | React 18 + Vite + Tailwind | 衣橱网格、对比视图、拖拽排序用模板语言写很痛苦；构建产物随包分发，用户电脑不需要 Node |
| 抠图 | `rembg`（U2Net，onnxruntime CPU） | 免费、离线、单张 1–2 秒 |
| 图像处理 | Pillow | 转正、缩放、EXIF 归一 |
| 打标 / 组套 / 判图 | 大模型适配层（多供应商） | 见 5.2 `clients` |
| 天气 | Open-Meteo（免 key） | 无需注册；国内精度不足时换和风天气适配器 |
| 二维码 | `qrcode` | 启动时终端打印，手机扫码进入 |

### 5.2 模块划分与契约

每个模块一个目录、一个明确职责、可单独调用、可单独重试。

```
capture.receive(file, kind)      -> {path, width, height}      只落盘转正，不判断内容
wardrobe.ingest(image_path)      -> GarmentDraft               抠图＋打标，不写库
wardrobe.confirm(draft, edits)   -> Garment                    写库
profiler.estimate(inputs)        -> BodyProfile                算式＋一次视觉调用
stylist.plan(ctx)                -> [Plan] × 3                 只出方案，不落库、不花钱
stylist.save(plan)               -> Outfit
renderer.render(outfit, ...)     -> {image, quality, fallback} 只出图，不选衣服
shopping.evaluate(image, ...)    -> Verdict
```

依赖方向单向：`web → stylist → wardrobe/db`，`web → renderer → clients`。`stylist` 不 import `renderer`，`renderer` 不 import `stylist`。

**三个刻意的设计决定：**

1. **`ingest` 与 `confirm` 分离。** 打标错一个颜色不必重拍；也让"批量入库 10 件"能先攒 draft 再逐条确认。
2. **`stylist` 不碰图，`renderer` 不选衣服。** 出图糊了只重渲，不重新搭配；搭配不满意只重配，不花出图钱。两者成本差 50 倍，合一很疼。
3. **候选池由规则生成，模型只在池子里挑。** 这是"十二月不推荐短袖"的唯一可靠保障，提示词约束大模型做不到。

### 5.3 目录结构

```
Outfit/
  outfit/
    __main__.py          启动：起服务、打印二维码
    config.py            配置与环境变量
    db.py                SQLite 连接、迁移
    models.py            SQLModel 表定义
    capture.py
    wardrobe.py
    profiler.py
    stylist/
      candidates.py      规则预筛
      scoring.py         软打分
      prompt.py          组装提示词
      plan.py            调用与解析
    renderer/
      compose.py         请求组装
      judge.py           忠实度校验
      board.py           降级：搭配板
    shopping.py
    clients/
      llm.py             视觉打标 / 组套 / 判图
      imagegen.py        多图合成（供应商适配器）
      weather.py
    web/
      api.py             REST 路由
      static/            构建产物
  web/                   前端源码（Vite）
  data/
    photos/              原始图（身体、衣服）
    cutouts/             抠图
    renders/             出图结果
    outfit.db
  docs/superpowers/specs/
  tests/
  .env                   密钥，已 gitignore
```

### 5.4 启动

Windows 双击 `启动.bat`，或 `python -m outfit`。行为：

1. 读 `.env`，缺 key 时进入"离线模式"（只能管衣橱和看规则方案，不能出图）；
2. 起 uvicorn，绑定 `0.0.0.0:8765`；
3. 终端打印本机局域网地址和二维码；
4. 同时打开桌面浏览器。

首次启动 Windows 会弹防火墙提示，需允许"专用网络"——README 里写明这一步。

---

## 6. 数据模型

```sql
CREATE TABLE body_profile (
  id            INTEGER PRIMARY KEY CHECK (id = 1),
  height_cm     REAL NOT NULL,
  weight_kg     REAL NOT NULL,
  chest_cm      REAL, waist_cm REAL, hip_cm REAL,
  shoulder_cm   REAL, inseam_cm REAL,
  body_shape    TEXT,        -- hourglass / pear / apple / rectangle / inverted_triangle
  skin_tone     TEXT,        -- cool / warm / neutral
  photo_full    TEXT,        -- 全身照相对路径
  photo_upper   TEXT,        -- 半身近照（看肤色更准）
  updated_at    TEXT NOT NULL
);

CREATE TABLE garment (
  id               INTEGER PRIMARY KEY,
  name             TEXT NOT NULL,
  category         TEXT NOT NULL,   -- top / bottom / outerwear / dress / shoes / bag / accessory
  subcategory      TEXT,            -- tee / shirt / knit / blazer / jeans / trousers / loafers ...
  color_primary    TEXT NOT NULL,   -- 色名，中文
  color_hex        TEXT,            -- 代表色值
  color_secondary  TEXT,
  pattern          TEXT,            -- solid / stripe / check / floral / graphic / other
  material         TEXT,            -- cotton / wool / denim / leather / knit / silk ...
  warmth           INTEGER NOT NULL,   -- 1..5
  formality        INTEGER NOT NULL,   -- 1..5
  seasons          TEXT,               -- JSON 数组 ["spring","winter"]
  style_tags       TEXT,               -- JSON 数组 ["minimal","commute"]
  fit              TEXT,               -- slim / regular / oversized
  brand            TEXT, size TEXT,
  image_path       TEXT NOT NULL,
  cutout_path      TEXT,
  label_confidence REAL NOT NULL,   -- 0..1
  wear_count       INTEGER NOT NULL DEFAULT 0,
  last_worn_at     TEXT,
  status           TEXT NOT NULL DEFAULT 'active',  -- active / stored / laundry / lent
  created_at       TEXT NOT NULL
);

CREATE TABLE outfit (
  id             INTEGER PRIMARY KEY,
  occasion       TEXT NOT NULL,
  temp_c         REAL,
  weather_text   TEXT,
  garment_ids    TEXT NOT NULL,   -- JSON 有序数组，首位 = 上装
  rationale      TEXT,
  coverage       TEXT,            -- full / upper_only / lower_only
  render_path    TEXT,
  render_status  TEXT NOT NULL DEFAULT 'none',  -- none / ok / rejected / degraded / failed
  render_quality REAL,
  is_saved       INTEGER NOT NULL DEFAULT 0,
  created_at     TEXT NOT NULL
);

CREATE TABLE shopping_verdict (
  id          INTEGER PRIMARY KEY,
  image_path  TEXT NOT NULL,
  verdict     TEXT NOT NULL,    -- buy / skip / depends
  reasons     TEXT,             -- JSON 数组
  pairs_with  TEXT,             -- JSON：garment id 数组
  created_at  TEXT NOT NULL
);

CREATE TABLE event (
  id         INTEGER PRIMARY KEY,
  type       TEXT NOT NULL,   -- render_requested / render_ok / render_rejected / plan_swapped ...
  payload    TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX idx_garment_status ON garment(status);
CREATE INDEX idx_garment_category ON garment(category);
CREATE INDEX idx_outfit_created ON outfit(created_at DESC);
```

图片按 `data/photos/<uuid>.jpg` 存，数据库只存相对路径，方便整目录搬迁。

---

## 7. 关键流程

### 7.1 首次设置（一次性，约 10 分钟）

1. 填身高体重；三围可不填，但填了判断更准。
2. 传一张全身照、一张自然光下的半身近照。
3. `profiler.estimate` 返回身形档与肤色冷暖，用户可改。
4. 录 10 件衣服，确认标签。

**不做伪精确的尺码换算。** 只有身高体重时，给的是"体型档 + 版型建议"（例如：矩形身形、建议 oversize 外套压肩线），不输出"S/M/L"。三围齐全时才算胸腰差、给具体的版型区间。

### 7.2 单件入库

```
拍照/选图 → capture（转正、缩到长边 1600）→ rembg 抠图
        → LLM 视觉打标（结构化 JSON）→ 预填确认表单
        → 用户确认/修改 → 入库
```

打标输出字段：`category, subcategory, color_primary, color_hex, pattern, material, warmth, formality, seasons, style_tags, fit, label_confidence`。

`label_confidence < 0.6` 时表单标黄，必须用户点过"确认"才写入——不允许静默落库。

### 7.3 每日穿搭

```
选场合（或输入一句话："明天 9 点面试"）→ 拉天气（失败则手输/用缓存）
→ candidates.build（规则预筛）→ stylist.plan（LLM 组 3 套）
→ 展示卡片 → 用户点"看效果" → renderer
```

场合输入支持自然语言，由 LLM 解析为 `{occasion, formality_range, note}`；解析失败则退回预设 chip。

### 7.4 出图与降级

```
Plan → compose（身体图 + 每件抠图 + 结构化描述）
     → imagegen（云端合成）
     → judge（另一次视觉调用：件数对不对、主色对不对、脸有没有被改）
     → 通过 → 保存，render_status = ok
     → 不通过 → 重试一次，缩成"三件以内"的简化版
     → 再不过 → board 降级：身体剪影 + 衣服抠图按穿搭位置排出搭配板
```

判定为"通过"的三条硬标准（缺一不可）：

1. 衣服件数与方案一致（鞋、包可缺，不计失败）；
2. 每件衣服代表色与数据库色值 HSL 距离在阈值内；
3. 脸部区域与原始身体照的感知相似度不低于阈值。

**降级不是失败。** 搭配板对衣服本身更忠实（合成图容易把格纹糊掉），很多人更愿意看这个。

### 7.5 买前判断

```
拍新衣服 → 抠图 + 打标（复用 wardrobe.ingest）
        → 与衣橱做匹配：能搭几件、补齐了什么空缺、和已有的是否重复
        → 结论：buy / skip / depends + 3 条理由 + 可搭配件
```

"重复"的判定：同品类、同主色、同正式度区间内已有 ≥2 件，则记重复。

---

## 8. 搭配规则

### 8.1 温区 → 厚薄

| 温区 | 温度 | 允许厚薄 | 外套 |
|---|---|---|---|
| 酷暑 | ≥ 28 | 1–2 | 不需要（薄外套可选） |
| 暖 | 22 – 27.9 | 1–3 | 可选 |
| 微凉 | 15 – 21.9 | 2–4 | 必需 |
| 冷 | 8 – 14.9 | 3–5 | 必需 |
| 严寒 | < 8 | 4–5 | 必需（厚） |

温度取"当日最高与最低的加权"：`0.6 × 出门时段温度 + 0.4 × 全天最低`，出门时段默认 8:00–9:00，可配置。

### 8.2 场合 → 正式度

| 场合 | 正式度区间 |
|---|---|
| 面试 | 4–5 |
| 上班 | 3–4 |
| 约会 | 2–4 |
| 运动 | 1–2 |
| 居家 | 1 |
| 自定义 | LLM 解析后映射到上表某一行，解析不出则 2–4 |

### 8.3 硬过滤（不满足直接剔除）

- `status != 'active'`
- `warmth` 不在温区允许范围
- `formality` 不在场合区间
- 最近 3 天穿过的单品（衣橱可用单品 < 8 件时放宽为 1 天）

### 8.4 软打分（权重）

```
score = 1.0 × 正式度契合（区间中位越近越高）
      + 0.8 × 配色和谐
      + 0.6 × 新鲜度（越久没穿越高）
      + 0.5 × 肤色契合（暖皮避开大面积冷灰粉，冷皮避开大面积橘棕）
      + 0.4 × 用户偏好（穿得多的、收藏过的加分）
      + 0.03 × 包/配饰件数（封顶 +0.12）
      - 0.7 × 与最近三套的重合度
```

两条实现时补的约束，写在这里以免以后被改回去：

- **单件均分只算上装/下装/外套/连衣裙/鞋**，配色和谐只算前四类。把包和配饰算进均值会让"件数越多分越低"，结果是包和手表永远选不上——这是实际跑出来才发现的。
- 包和配饰不在均值里，改成固定加成。它们的价值是"完整度"，不是"多一件多一分"。

配色和谐规则（用 HSL 判断）：

- 同色系：主色相差 < 20°，加分最多；
- 邻近色：相差 20–60°；
- 对比色：相差 > 120°，且至少一件是中性色（黑/白/灰/米/藏蓝），否则扣分；
- 两件高饱和且明度接近，扣分（"打架"）。

### 8.5 组套约束

- 必须 (1 上装 + 1 下装) 或 (1 连衣裙)；温区要求外套时必须有 1 件外套；
- 鞋恰好 1 双；包 0–1 个；配饰 0–2 件；
- 三套方案的核心单品（上装/下装/外套/连衣裙）不能完全相同，且选取后续方案时按重合比例扣 0.20×重合度；衣橱撑不住时退到"不完全相同"即可，宁可三套相近也不给一套。
- 三套方案按角色标注：**首选**（综合最高）、**更正式**（正式度接近该衣橱上限）、**更舒服**（舒适度接近上限）。

---

## 9. 界面

手机优先，单列，大按钮，深色底配柔和中性色（衣服颜色是主角，界面不该抢色）。

| 页面 | 元素 |
|---|---|
| **今天** | 场合 chips（面试/上班/约会/运动/居家/自定义）＋ 天气卡（温度、体感、降水、一句话建议）＋ "生成" 按钮 → 3 张方案卡：衣物缩略图横排、理由一句话、"看上身效果"、"换一套" |
| **衣橱** | 网格（2 列），顶部按品类筛，角标显示状态；点开进编辑：改标签、标记收起来/送洗、看穿着次数 |
| **入库** | 拍照/选图 → 进度条（抠图中 → 打标中）→ 确认表单：颜色用大色块选、标签可点改、"存" |
| **我的** | 身高体重三围、身体照片（可重拍）、肤色、体型档、采集规范提示 |
| **买不买** | 拍一件 → 结论卡：大字结论、3 条理由、"能和这 3 件搭"缩略图、"还是算了" |

出图是**按需触发**，不是自动——每张都在花钱，必须用户点。

---

## 10. 错误处理矩阵

| 故障 | 表现 | 处理 |
|---|---|---|
| 无网络 | 首页仍可用 | 天气用缓存并标注"昨天的天气"；"看效果"置灰并说明原因 |
| 天气 API 失败 | 天气卡为空 | 手输温度，或点"用昨天" |
| 抠图失败 | 入库卡住 | 保留原图铺白底，标"未抠图"，不阻断入库 |
| 打标失败 | 表单为空 | 全部字段待手填，提示"这次没认出来" |
| 标签置信度 < 0.6 | 表单标黄 | 必须点确认才保存 |
| 出图被安全策略拒 | 卡片显示失败 | 明说"这张被拒了，加件外套或换套方案再试"，不静默转圈 |
| 出图超时 | 30 秒转圈 | 超时即降级到搭配板，后台继续跑，好了替换 |
| 视觉校验不通过 | 不出图 | 自动重试简化版一次，再不过走搭配板 |
| API 额度用尽 | 出图报错 | 顶部横幅"今日额度用完，明天恢复"，方案照常可看 |
| 数据库损坏 | 启动报错 | 启动时自检；损坏则重命名旧库并新建，提示"衣橱数据需重建" |

所有失败必须**给出下一步动作**，不允许只显示"出错了"。

---

## 11. 成本与限额

| 项 | 单价 | 频次 | 月成本 |
|---|---|---|---|
| 入库打标 | ¥0.01–0.03 / 件 | 一次性 + 偶尔 | 首次 ¥0.3 |
| 组套 | ¥0.05–0.15 / 次 | 每天 1–2 次 | ¥3–9 |
| 出图 | ¥0.2–0.5 / 张 | 每天 1–3 张 | ¥15–30 |
| 判图（买不买） | ¥0.05 / 次 | 偶尔 | ¥1–2 |
| **合计** | | | **¥20–40** |

硬限额：

- 每天合成图 ≤ 6 张（在 `event` 表计数，跨设备一致）；
- 同一套方案 24 小时内缓存结果，重复点"看效果"不再扣费；
- 超额后只能看搭配板。

界面上要能看到"今天已出 3 张"，让花费是可见的。

---

## 12. 隐私与安全

- 原始照片只存 `data/`，不出本机；云端每次只收到"这一次合成所需的那几张"，不落库、不留存。
- 无账号、无遥测、无崩溃上报。
- `.env` 存密钥，`.gitignore` 包含 `.env` 和 `data/`。
- 服务绑定局域网，不做公网穿透、不做端口映射。
- 启动时打印二维码只在终端，不上传。
- 提供"一键清空数据"：删 `data/` 后重启即恢复初始态。

---

## 13. 测试

| 层 | 内容 |
|---|---|
| 单元 | 温区→厚薄映射、正式度区间、池子硬过滤边界（12 月不得出现短袖）、配色打分、组套约束校验 |
| 集成 | 3 张预置图跑通"入库→组套→出图"，`imagegen` 与 `llm` 用假适配器，零花费 |
| 契约 | 每个适配器按共同接口跑同一组用例，保证换供应商不回归 |
| 冒烟 | 真图手动跑一遍，肉眼看脸和衣服对不对（人工，不进 CI） |
| 视觉回归 | 五个页面截图对比，防止改样式改崩 |

假适配器（`FakeImageGen` / `FakeLLM`）从第一天就写，保证 CI 不花钱、不联网。

---

## 14. 里程碑

| 阶段 | 交付 | 验收 |
|---|---|---|
| **M1 能看方案** | 衣橱入库、身体档案、规则预筛 + 组套、今天页、衣橱页 | 录 10 件衣服，早上能出 3 套说得通的方案，不接任何出图 API |
| **M2 能看效果** | 出图适配器、忠实度校验、搭配板降级、入库页、我的页 | 三套里至少一套出图成功；故意断网/拒图时能正确降级 |
| **M3 能判断买** | 买不买页、匹配逻辑 | 拍一件新衣服，结论和理由说得通 |
| **M4 打磨** | 视觉回归、错误态文案、成本可见、一键清空 | 全部错误态都有下一步动作 |

M1 就能验证"这事值不值得做"，M2 才是这个产品的核心体验。

---

## 15. 决策记录（为什么不是别的）

| 决定 | 备选 | 为什么否掉备选 |
|---|---|---|
| 单体本地服务 | Agent 框架（LangGraph 类） | 难点在标签质量与出图保真，不编排；框架让"单独重跑一步"变难，且每步都计费 |
| 单体本地服务 | 托管工作流（扣子/n8n） | 身体照片要上第三方；试穿那步无法精细控制 |
| 多图合成出图 | 传统 VTON 串行换装 | 四五轮叠加后人体比例崩，配饰鞋包难处理 |
| 规则预筛 + LLM 组套 | 全衣橱塞进 prompt | 超过 50 件开始胡说，且无法保证季节/场合硬约束 |
| 默认国内可直连模型 | Gemini 2.5 Flash Image 为默认 | 大陆需代理，不适合"每天早上用"的链路；保留为可选适配器 |
| 手机浏览器 | 纯桌面 App | 拍衣服只能在手机上拍，先传电脑再入库会把使用成本抬高到没人用 |
| 出图按需触发 | 生成方案时自动出图 | 每张 ¥0.2–0.5，自动出图会让人不敢点"生成" |
| 不采用裸照 | — | 安全过滤会拒图、贴身衣物更准、泄露代价不可换 |

---

## 16. v2 候选（本版不做）

- 从电商商品页/截图批量导入
- 行程级打包与出差清单
- 穿着记录 → 衣柜利用率报告（"这 12 件你一年没穿了"）
- 洗衣提醒、换季收纳
- 与日历联动（明天有会，提前一晚提醒）
