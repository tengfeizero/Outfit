# 本地 AI 穿搭助手

装在自己笔记本上的穿搭助手：告诉它身高体重和衣橱，它按场合和天气给三套方案。
照片只存在本机，手机连同一个 Wi-Fi 就能用。

- 设计文档：[docs/superpowers/specs/2026-11-06-ai-outfit-agent-design.md](docs/superpowers/specs/2026-11-06-ai-outfit-agent-design.md)

- 实现计划：[docs/superpowers/plans/2026-11-06-outfit-implementation-plan.md](docs/superpowers/plans/2026-11-06-outfit-implementation-plan.md)

- 架构与选型：[docs/architecture.md](docs/architecture.md) —— 循环怎么跑、失败怎么兜、以及"为什么不用 agent 框架"

## 它是 agent 吗

是，但要说清楚是哪种：**工具调用循环 + 失败降级，不是自主规划的 multi-agent。**

说一句话（"明天上午面试，外面有点冷"），模型自己决定先查天气、再检索衣橱、再组套，每一步的想法和结果都留在轨迹里，前端可以看到。最多 6 步、¥1.2、2 张图，超了就停。

没配模型时它退化成确定性流水线——照样出方案，只是不会自己决定步骤。

## 现在能用到什么程度

| 功能 | 状态 |
|---|---|
| 衣橱录入（拍一张，主色自动认，点两下存） | ✅ 可用 |
| 衣服自动抠图 | ✅ 已装好；模型在 `data/models`，跟数据放一起 |
| 三个方案的搭配（规则 + 打分，不花钱） | ✅ 可用 |
| 身体档案、体型建议 | ✅ 可用 |
| 天气自动取温（「我的」里设城市） | ✅ 可用 |
| 手机浏览器访问 | ✅ 可用 |
| 搭配图（把一套拼成一张可保存的图） | ✅ 本地生成，不花钱 |
| 买前判断（重复 / 互补 / 空缺） | ✅ 规则版，不联网 |
| 自动打标（拍照认出品类/颜色/厚薄/正式度） | ✅ 混元视觉，云端 |
| 照片级上身效果图（你穿着它） | ✅ 混元出图，带忠实度校验 |
| 试穿图每日限额 | ✅ 每天 6 张，用完退搭配板 |

没配密钥时是**离线模式**：搭配、衣橱、天气、抠图、搭配图、买前判断全都可用，只是不能自动打标和出照片级效果图，也不会报错。

## 安装

需要 Python 3.10+。第一次：

```bat
双击 启动.bat
```

它会自动建虚拟环境、装依赖、起服务，然后打印一个二维码。

抠图是可选的。这台机器上已经装好了；换台机器想要自动去背景，再装一次：

```bat
.venv\Scripts\python.exe -m pip install rembg onnxruntime
```

第一次抠图会下载一个约 170MB 的模型，存到 `data/models/u2net.onnx`，之后都离线。装不上也没关系——入库照样能用，只是照片保留原样。

## 用

1. 双击 `启动.bat`，那个黑窗口不要关。
2. 电脑上打开 http://127.0.0.1:8765
3. 手机（同一个 Wi-Fi）扫窗口里的二维码，或手动输入窗口里那个 `http://192.168.x.x:8765`。

第一次启动 Windows 会问防火墙，**勾「专用网络」再允许**，否则手机连不进来。

## 接入模型（可选）

不配也能用，只是少了"自动认衣服"和"试穿效果图"。

1. 去 [TokenHub 控制台](https://console.cloud.tencent.com/tokenhub/apikey) 拿一个 API Key。
2. 在控制台的在线推理里给 `hy-vision-2.0-instruct`（认衣服）和 `hy-image-v3.5-preview`（出图）**开启后付费**。只拿 key 不开后付费，调用会返回 `quota exhausted`。
3. 把 key 写进 `.env`：

```
TOKENHUB_API_KEY=sk-...
```

打标用的是 `hy-vision-2.0-instruct`，出图用的是 `hy-image-v3.5-preview`。两者都在 `outfit/clients/tokenhub.py` 一个文件里，换供应商只改这个文件。

## 换一台机器接着开发

仓库里**只有代码**：照片、数据库、模型文件、密钥都不在（见 `.gitignore`）。所以新机器上：

```bat
git clone <你的仓库地址>
cd Outfit

:: 1. 建环境（Python 3.10+）
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

:: 2. 配密钥（没有也能跑，只是不能自动打标和出图）
copy .env.example .env
:: 打开 .env 填 TOKENHUB_API_KEY

:: 3. 灌一套演示衣橱（数据库是空的）
.venv\Scripts\python.exe -m outfit.demo --reseed

:: 4. 验证环境
.venv\Scripts\python.exe -m pytest tests -q

:: 5. 启动
双击 启动.bat
```

**前端不用装 Node**：`outfit/web/static/` 里的构建产物跟着仓库走，直接能用。只有要改前端时才需要：

```bat
cd web
npm install
npm run build
```

**要带走的私有数据**（旧机器上）就三样：`data/`（衣橱和照片）、`.env`（密钥）、可选 `data/models/u2net.onnx`（168MB 抠图模型，不带的话第一次抠图会自动下载）。

---

## 改前端

```bat
cd web
npm install
npm run build
```

构建产物直接输出到 `outfit/web/static`，服务不用重启，刷新页面即可。

## 数据放哪

```
data/
  outfit.db      衣橱、档案、方案记录
  photos/        原始照片
  cutouts/       抠好的图
  renders/       出图结果
```

备份就是复制整个 `data/` 目录。想清空就删掉它，重启即恢复初始状态。

## 跑测试

```bat
.venv\Scripts\python.exe -m pytest tests -q
```

144 项，全部不联网、不花钱。里面有一条是硬的：**十二月的候选池里不许出现短袖**；另一条守的是"打开一片黑"——`.js` 必须以 `text/javascript` 发出去。

## 命令行试跑（不开界面）

```bat
.venv\Scripts\python.exe -m outfit.demo --occasion work --temp 18
```

`--reseed` 会重建那套 19 件的演示衣橱。
