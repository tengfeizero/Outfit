# 本地 AI 穿搭助手

装在自己笔记本上的穿搭助手：告诉它身高体重和衣橱，它按场合和天气给三套方案。
照片只存在本机，手机连同一个 Wi-Fi 就能用。

设计文档：[docs/superpowers/specs/2026-11-06-ai-outfit-agent-design.md](docs/superpowers/specs/2026-11-06-ai-outfit-agent-design.md)
实现计划：[docs/superpowers/plans/2026-11-06-outfit-implementation-plan.md](docs/superpowers/plans/2026-11-06-outfit-implementation-plan.md)

## 现在能用到什么程度

| 功能 | 状态 |
|---|---|
| 衣橱录入（拍一张，主色自动认，点两下存） | ✅ 可用 |
| 衣服自动抠图 | ✅ 装了 rembg 就自动抠；没装就保留原图，不报错 |
| 三个方案的搭配（规则 + 打分，不花钱） | ✅ 可用 |
| 身体档案、体型建议 | ✅ 可用 |
| 天气自动取温（「我的」里设城市） | ✅ 可用 |
| 手机浏览器访问 | ✅ 可用 |
| 自动打标（认出品类/厚薄/正式度） | ⬜ 需要模型 key |
| 上身效果图 | ⬜ 未接（M2） |
| 买前判断 | ⬜ 未接（M3） |

没配密钥时是**离线模式**：搭配、衣橱、天气、抠图全都可用，只是不能自动打标和出图，也不会报错。

## 安装

需要 Python 3.10+。第一次：

```bat
双击 启动.bat
```

它会自动建虚拟环境、装依赖、起服务，然后打印一个二维码。

抠图是可选的。想要衣服自动去背景，再装一次：

```bat
.venv\Scripts\python.exe -m pip install rembg
```

第一次抠图会下载一个约 170MB 的模型，之后都离线。装不上也没关系——入库照样能用，只是照片保留原样。

## 用

1. 双击 `启动.bat`，那个黑窗口不要关。
2. 电脑上打开 http://127.0.0.1:8765
3. 手机（同一个 Wi-Fi）扫窗口里的二维码，或手动输入窗口里那个 `http://192.168.x.x:8765`。

第一次启动 Windows 会问防火墙，**勾「专用网络」再允许**，否则手机连不进来。

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

74 项，全部不联网、不花钱。里面有一条是硬的：**十二月的候选池里不许出现短袖**；另一条守的是"打开一片黑"——`.js` 必须以 `text/javascript` 发出去。

## 命令行试跑（不开界面）

```bat
.venv\Scripts\python.exe -m outfit.demo --occasion work --temp 18
```

`--reseed` 会重建那套 19 件的演示衣橱。
