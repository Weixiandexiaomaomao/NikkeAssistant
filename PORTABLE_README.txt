妮姬国服助手 v0.3.37 · Windows 64 位便携测试版

# 妮姬国服助手 · NikkeAssistant

基于 MaaFramework 的 Windows 日常自动化工具，面向雷电模拟器中的《胜利女神：新的希望》国服。

## 下载与运行

**普通用户请到 [Releases](https://github.com/Weixiandexiaomaomao/NikkeAssistant/releases) 下载 `NikkeAssistant-0.3.37-win-x64.zip`。** GitHub 的 Source code 压缩包是源码，不是可直接运行的程序。

1. 完整解压 Windows 64 位便携包，不要只复制 EXE，无需安装 Python。
2. 启动雷电模拟器，使用竖屏 9:16，例如 1080×1920 或 720×1280。
3. 双击 `NikkeAssistant.exe`。助手会检测雷电 ADB 和设备；无法检测时，在连接设置中手动选择雷电目录中的 `adb.exe` 和对应实例。
4. 勾选需要执行的任务，点击“开始任务”。“启动游戏”任务会启动已安装的国服游戏，处理已适配公告并检查大厅。
5. 可点击“停止任务”或使用 F8 停止。

下载包不含个人设置、账号资料、日志、截图或旧版本备份。首次运行会在程序目录生成设置和运行记录。

## 功能

- 邮箱、好友点数、前哨基地收菜、免费歼灭和派遣领取。
- 普通商店免费商品购买、一次免费刷新及刷新后免费商品购买。
- 付费商店内的每日、每周、每月免费礼包与可直接领取的免费 STEP UP 阶段。
- 模拟室快速模拟、拦截战优先快速战斗及不可用时的实际战斗。
- 企业塔、新人竞技场免费挑战、特殊竞技场奖励和批量咨询。
- 咨询列表中的角色花絮红点、剧情跳过及章节奖励领取。
- 每日免费单抽、获得角色展示跳过和招募结果确认。
- 活动签到、STORY、挑战和活动任务；STORY II 开放后优先检查未通关新关卡。
- 普通任务与 PASS 奖励最后领取；过程中处理已识别的奖励与礼包推销弹窗。

操作使用已有免费次数和门票，不自动购买付费次数。出现未识别页面会记录失败，确认能恢复后才继续下一项。

## 当前状态

**v0.3.37 为测试版。** 开发环境 106 项自动测试和便携包自检通过。公开源码排除了账号截图，对应 4 项截图回放测试会跳过，其余 102 项可运行。STORY II 新页面经过真实 Maa OCR 截图回放验证；完整首次推图战斗仍未完成实机验证。活动页面、开放日期及游戏界面变化可能影响识别。实际战斗沿用游戏内当前队伍，需要开启自动射击和自动爆裂。

## 开发与构建

需要 Windows 64 位 Python 3.10。源码包含运行资源、OCR 模型、任务定义和测试。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

构建便携版见 [BUILD.md](BUILD.md)。第三方组件及 OCR 模型说明见 [licenses](licenses)。

## 开源许可与反馈

本项目原创应用代码使用 [Apache License 2.0](LICENSE)。第三方组件分别遵循其原有许可证，游戏相关名称及图像归各自权利人所有。

发现问题可在 [Issues](https://github.com/Weixiandexiaomaomao/NikkeAssistant/issues) 提交版本、模拟器分辨率、任务名称及复现步骤；截图和日志请先遮挡账号等个人信息。本工具为非官方项目。
