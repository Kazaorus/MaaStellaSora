<!-- markdownlint-disable MD033 MD041 -->

<div align="center">
    <img src="assets/logo.png" alt="StellaSora-Auto-Helper" width="200" />
    <h1>MaaStellaSora</h1>
    <p>星塔助手（MaaStellaSora）提供自动签到、清理日常等功能，由 MaaFramework 强力驱动</p>
</div>

遇到问题请去Issues反馈，或前往QQ交流群进行反馈

QQ交流群：**1063132902**  密码：**星塔旅人**

> 项目当前仍处于预览版，可能会遇到部分问题

## 功能

- [x] 登录游戏并签到
- [x] 清理活动
- [x] 赠礼
- [x] 五次邀约
- [x] 领取&发送好友干劲
- [x] 领取委托并重新派遣
- [x] 领取任务
- [x] 自动爬塔
- [x] 自动进行指定关卡
- [x] 真格挑战
- [x] 猎影合围

## 安装与使用

> 星塔助手目前只对比例为16:9的游戏客户端提供支持，如果你的游戏客户端比例不为16:9请自行寻找改分辨率方法或是使用模拟器

1. 前往 [GitHub Releases](https://github.com/MaaStellaSora/MaaStellaSora/releases) 下载对应系统的压缩包。
2. 根据需要选择 GUI：
   - **MFAAvalonia（推荐）**：下载 `MaaStellaSora-{系统}-{架构}-vX.Y.Z.zip`（Windows）或对应的 `.tar.gz`（Linux/macOS），支持现有全部发布平台及自动更新。
   - **MXU**：Windows x64 用户可下载 `MaaStellaSora-mxu-win-amd64-vX.Y.Z.zip`。MXU 当前不支持自动更新，后续版本需重新前往 GitHub Releases 下载。
3. 将压缩包完整解压到任意目录，运行包内的 MFAAvalonia 主程序；MXU 用户运行 `mxu.exe`。
4. 如果需要操控 Windows 版《星塔旅人》，请使用管理员权限运行 GUI；使用 ADB 时可直接启动。

### Windows 桌面端自动启动

在发行版的根目录下新增`start_windows`文件夹，将其中的`start_windows.exe`加入Windows任务计划即可定时自动启动。

注册任务计划时务必勾选“只在用户登录时运行”和“使用最高权限运行”。
此外，在任务计划的 操作→启动程序→设置→添加参数 中填入以下内容：

```text
--launcher "C:\path\to\your\launcher" --gui "C:\path\to\your\gui"
```

- `C:\path\to\your\launcher`改为你的游戏启动器路径，建议填写绝对路径
- `C:\path\to\your\gui`改为脚本中`MFAAvalonia.exe`的路径，建议填写绝对路径

---

Windows 桌面端需要先启动游戏启动器，再点击启动器中的“开始游戏”。`start_windows` 是由 Windows 计划任务启动的工作程序：它会先完成游戏启动，检测到游戏主窗口后再启动 MFAAvalonia 或 MXU。不要将它配置到 MFAAvalonia/MXU 的“启动前脚本”中，否则 GUI 的窗口检测仍会与工作程序并行执行。

启动脚本计划任务只需由管理员注册一次，正常运行不应弹出 UAC。任务计划必须设置为“仅当用户登录时运行”和“使用最高权限运行”，并使用当前用户的交互式桌面；不要使用 `SYSTEM`。建议将工作程序、MFA/MXU 包、内置 Python、Agent 和资源放在普通用户不能修改的目录中。

需要构建 EXE 时，在已安装 MaaFramework Python 依赖的 Windows 环境执行：

```powershell
python -m pip install -r requirements-build.txt
git submodule update --init assets/MaaCommonAssets
python tools/ci/configure.py
python tools/build_start_windows_exe.py
```

构建结果为 `dist\start_windows\start_windows.exe`，必须连同同目录下的 `resource` 文件夹一起保留；资源目录必须包含 `resource\base\model\ocr`。若当前源码目录没有完整资源，可使用已准备好的资源目录：

```powershell
python tools/build_start_windows_exe.py --resource-root "C:\path\to\resource"
```

在任务计划程序中创建按需任务，操作设置为：

- 程序：`C:\path\to\dist\start_windows\start_windows.exe`
- 起始于：`C:\path\to\dist\start_windows`
- 参数：根据实际使用的 GUI 选择以下一组

MFAAvalonia：

```powershell
.\dist\start_windows\start_windows.exe --launcher "C:\path\to\StellaSora_CN_Gamelauncher.exe" --gui "C:\path\to\MFAAvalonia.exe"
```

MXU：

```powershell
.\dist\start_windows\start_windows.exe --launcher "C:\path\to\StellaSora_CN_Gamelauncher.exe" --gui "C:\path\to\mxu.exe"
```

发布包使用包内 Python；源码环境也可以直接使用 `python start_windows.py --launcher ... --gui ...`。`--launcher` 可以省略，此时脚本会复用已经存在的启动器窗口；提供 `--launcher` 时，脚本还会校验窗口所属进程确实是该 EXE，避免把 IDE 或资源管理器中包含 `StellaSora` 的窗口误当成启动器；`--gui` 必须指向实际的 MFAAvalonia 或 MXU 可执行文件。工作程序会等待游戏主窗口标题匹配 `xtlr`、`星塔旅人`、`ステラソラ` 或 `StellaSora` 后再启动 GUI。启动器窗口通过 MaaFramework 的 Win32 后台输入方式操作，不要求启动器位于最前台或置顶；`SendMessageWithCursorPos` 可能会短暂移动鼠标并在操作后恢复。

## 参与开发或贡献

详见 [参与 MaaStellaSora 贡献](./CONTRIBUTING.md)

## 鸣谢

本项目由 **[MaaFramework](https://github.com/MaaXYZ/MaaFramework)** 强力驱动！

本项目部分功能使用 **[MaaPipelineEditor](https://github.com/kqcoxn/MaaPipelineEditor)** 进行辅助编辑

感谢以下开发者对本项目作出的贡献:

[![Contributors](https://contrib.rocks/image?repo=SodaCodeSave/StellaSora-Auto-Helper&max=1000)](https://github.com/SodaCodeSave/StellaSora-Auto-Helper/graphs/contributors)

## 相关项目

- **[MaaFramework](https://github.com/MaaXYZ/MaaFramework)** 基于图像识别的自动化黑盒测试框架
- **[MFAAvalonia](https://github.com/MaaXYZ/MFAAvalonia)** 基于 Avalonia 的通用 GUI，由 MaaFramework 强力驱动
- **[MXU](https://github.com/MistEO/MXU)** 基于 Web 技术的 MaaFramework 通用 GUI
- **[MaaPipelineEditor](https://github.com/kqcoxn/MaaPipelineEditor)** 可视化阅读与构建 Pipeline，功能完备，极致轻量跨平台，提供渐进式本地功能扩展，无缝兼容新旧项目
