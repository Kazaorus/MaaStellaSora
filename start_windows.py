#!/usr/bin/env python3
"""Start the Windows launcher in the background and wait for the game window."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Pattern, Sequence


LAUNCHER_ENTRY = "启动器_开始游戏"
DEFAULT_LAUNCHER_TITLE_REGEX = r"(?i)(\bstella\s*sora\b|星塔旅人|launcher)"
DEFAULT_MAIN_TITLE_REGEX = r"(?i)(xtlr|星塔旅人|ステラソラ|StellaSora)"
DEFAULT_MAIN_CLASS_REGEX = r"UnityWndClass"
DEFAULT_BUTTON_TEXTS = ("开始游戏", "Start Game", "ゲーム開始")


class LaunchError(RuntimeError):
    """A user-actionable launcher workflow failure."""


@dataclass(frozen=True)
class LaunchConfig:
    project_root: Path
    launcher_path: Path | None
    gui_path: Path
    launcher_title_regex: str
    launcher_class_regex: str | None
    main_title_regex: str
    main_class_regex: str | None
    launcher_timeout: float
    main_timeout: float
    poll_interval: float
    button_texts: tuple[str, ...]
    resource_root: Path | None = None


@dataclass(frozen=True)
class RuntimeBindings:
    initialize: Callable[[Path], None]
    find_windows: Callable[[], Sequence[Any]]
    click_launcher: Callable[[Any, LaunchConfig], None]


def _compile(pattern: str | Pattern[str] | None) -> Pattern[str] | None:
    if pattern is None:
        return None
    if hasattr(pattern, "search"):
        return pattern
    return re.compile(pattern, re.IGNORECASE)


def _get_window_process_path(window: Any) -> Path | None:
    """Return the executable path for a desktop window's owning process."""

    if sys.platform != "win32":
        return None

    import ctypes
    from ctypes import wintypes

    hwnd = getattr(window, "hwnd", None)
    if isinstance(hwnd, ctypes.c_void_p):
        hwnd = hwnd.value
    if not hwnd:
        return None

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    if not user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id)):
        return None

    process_query_limited_information = 0x1000
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    process_handle = kernel32.OpenProcess(
        process_query_limited_information,
        False,
        process_id,
    )
    if not process_handle:
        return None

    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        if not kernel32.QueryFullProcessImageNameW(
            process_handle,
            0,
            buffer,
            ctypes.byref(size),
        ):
            return None
        return Path(buffer.value)
    finally:
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle(process_handle)


def _normalized_path(path: Path) -> str:
    return str(path.expanduser().resolve()).casefold()


def find_matching_window(
    windows: Sequence[Any],
    title_pattern: str | Pattern[str],
    class_pattern: str | Pattern[str] | None = None,
    *,
    process_path: Path | None = None,
    process_path_getter: Callable[[Any], Path | None] | None = None,
) -> Any | None:
    """Return the first Maa desktop window matching the requested identity."""

    title_re = _compile(title_pattern)
    class_re = _compile(class_pattern)
    assert title_re is not None
    expected_process_path = (
        _normalized_path(process_path) if process_path is not None else None
    )
    get_process_path = process_path_getter or _get_window_process_path

    for window in windows:
        title = getattr(window, "window_name", "") or ""
        class_name = getattr(window, "class_name", "") or ""
        if not title_re.search(title):
            continue
        if class_re is not None and not class_re.search(class_name):
            continue
        if expected_process_path is not None:
            actual_process_path = get_process_path(window)
            if (
                actual_process_path is None
                or _normalized_path(actual_process_path) != expected_process_path
            ):
                continue
        return window
    return None


def wait_for_window(
    find_windows: Callable[[], Sequence[Any]],
    matcher: Callable[[Sequence[Any]], Any | None],
    timeout: float,
    poll_interval: float,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Poll desktop windows until ``matcher`` returns a window or times out."""

    if timeout <= 0 or poll_interval <= 0:
        raise LaunchError("窗口等待参数必须大于 0")

    deadline = clock() + timeout
    while True:
        window = matcher(find_windows())
        if window is not None:
            return window

        remaining = deadline - clock()
        if remaining <= 0:
            raise LaunchError("等待目标窗口超时")
        sleep(min(poll_interval, remaining))


def _resolve_launcher_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise LaunchError(f"游戏启动器不存在: {resolved}")
    return resolved


def _resolve_gui_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise LaunchError(f"MFAAvalonia/MXU 程序不存在: {resolved}")
    return resolved


def _start_process(
    path: Path,
    label: str,
    start_process: Callable[..., Any],
    *,
    require_running: bool = False,
) -> Any:
    try:
        process = start_process(
            [str(path)],
            cwd=str(path.parent),
            shell=False,
        )
    except OSError as error:
        raise LaunchError(f"启动{label}失败: {error}") from error

    poll = getattr(process, "poll", None)
    if require_running and callable(poll) and poll() is not None:
        raise LaunchError(f"{label}启动后立即退出")
    return process


def _resource_root(config: LaunchConfig) -> Path:
    candidates = []
    if config.resource_root is not None:
        candidates.append(config.resource_root.expanduser().resolve())
    candidates.extend(
        (
            config.project_root / "assets" / "resource",
            config.project_root / "resource",
        )
    )
    for candidate in candidates:
        if (candidate / "base").is_dir() and (candidate / "windows").is_dir():
            return candidate
    raise LaunchError("未找到 Maa 资源目录，需要同时包含 resource/base 和 resource/windows")


def _load_runtime(project_root: Path) -> RuntimeBindings:
    try:
        from maa.controller import (
            MaaWin32InputMethodEnum,
            MaaWin32ScreencapMethodEnum,
            Win32Controller,
        )
        from maa.resource import Resource
        from maa.tasker import Tasker
        from maa.toolkit import Toolkit
    except ImportError as error:
        raise LaunchError(
            "无法导入 MaaFramework Python 依赖，请使用发布包内的 Python 或安装 requirements.txt"
        ) from error

    def initialize(root: Path) -> None:
        Toolkit.init_option(str(root))

    def find_windows() -> Sequence[Any]:
        return Toolkit.find_desktop_windows()

    def click_launcher(window: Any, config: LaunchConfig) -> None:
        resources = Resource()
        resource_root = _resource_root(config)
        for bundle in (resource_root / "base", resource_root / "windows"):
            job = resources.post_bundle(bundle).wait()
            if not job.succeeded:
                raise LaunchError(f"Maa 资源加载失败: {bundle}")

        controller = Win32Controller(
            window.hwnd,
            screencap_method=MaaWin32ScreencapMethodEnum.Background,
            mouse_method=MaaWin32InputMethodEnum.SendMessageWithCursorPos,
            keyboard_method=MaaWin32InputMethodEnum.SendMessageWithCursorPos,
        )
        try:
            if not controller.post_connection().wait().succeeded:
                raise LaunchError("无法连接游戏启动器窗口")

            tasker = Tasker()
            if not tasker.bind(resources, controller):
                raise LaunchError("无法绑定启动器 Maa 资源和 Controller")

            job = tasker.post_task(
                LAUNCHER_ENTRY,
                {
                    LAUNCHER_ENTRY: {
                        "recognition": {
                            "param": {"expected": list(config.button_texts)},
                        }
                    }
                },
            ).wait()
            if not job.succeeded:
                raise LaunchError("未识别到启动器的开始游戏按钮，或后台点击失败")
        finally:
            try:
                controller.post_inactive().wait()
            except Exception:
                pass

    return RuntimeBindings(initialize, find_windows, click_launcher)


def run_workflow(
    config: LaunchConfig,
    *,
    bindings: RuntimeBindings | None = None,
    start_process: Callable[..., Any] = subprocess.Popen,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Run the launcher-to-game-to-GUI handoff for the scheduled worker."""

    if sys.platform != "win32":
        raise LaunchError("start_windows.py 仅支持 Windows")

    gui_path = _resolve_gui_path(config.gui_path)
    bindings = bindings or _load_runtime(config.project_root)
    bindings.initialize(config.project_root)

    main_matcher = lambda windows: find_matching_window(
        windows, config.main_title_regex, config.main_class_regex
    )
    main_window = main_matcher(bindings.find_windows())
    if main_window is None:
        launcher_path = (
            _resolve_launcher_path(config.launcher_path)
            if config.launcher_path is not None
            else None
        )

        launcher_matcher = lambda windows: find_matching_window(
            windows,
            config.launcher_title_regex,
            config.launcher_class_regex,
            process_path=launcher_path,
        )
        launcher_window = launcher_matcher(bindings.find_windows())
        if launcher_window is None:
            if launcher_path is None:
                raise LaunchError(
                    "未找到游戏主窗口或启动器窗口，请使用 --launcher 指定启动器 exe"
                )
            _start_process(launcher_path, "游戏启动器", start_process)
            launcher_window = wait_for_window(
                bindings.find_windows,
                launcher_matcher,
                config.launcher_timeout,
                config.poll_interval,
                clock=clock,
                sleep=sleep,
            )

        bindings.click_launcher(launcher_window, config)
        wait_for_window(
            bindings.find_windows,
            main_matcher,
            config.main_timeout,
            config.poll_interval,
            clock=clock,
            sleep=sleep,
        )

    _start_process(
        gui_path,
        "MFAAvalonia/MXU",
        start_process,
        require_running=True,
    )


def default_project_root() -> Path:
    """Return the directory containing external runtime resources."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _parse_args(argv: Sequence[str] | None = None) -> LaunchConfig:
    parser = argparse.ArgumentParser(
        description="后台启动《星塔旅人》启动器，等待游戏主窗口后返回成功"
    )
    project_root = default_project_root()
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument("--resource-root", type=Path)
    parser.add_argument("--launcher", type=Path, help="游戏启动器 exe 路径")
    parser.add_argument(
        "--gui",
        type=Path,
        required=True,
        help="MFAAvalonia 或 MXU 可执行文件路径",
    )
    parser.add_argument("--launcher-window-regex", default=DEFAULT_LAUNCHER_TITLE_REGEX)
    parser.add_argument("--launcher-class-regex")
    parser.add_argument("--main-window-regex", default=DEFAULT_MAIN_TITLE_REGEX)
    parser.add_argument("--main-class-regex", default=DEFAULT_MAIN_CLASS_REGEX)
    parser.add_argument(
        "--button-text",
        action="append",
        dest="button_texts",
        help="启动按钮 OCR 文本，可重复指定；默认支持中/英/日",
    )
    parser.add_argument("--launcher-timeout", type=float, default=30)
    parser.add_argument("--main-timeout", type=float, default=180)
    parser.add_argument("--poll-interval", type=float, default=0.5)
    args = parser.parse_args(argv)

    button_texts = tuple(args.button_texts or DEFAULT_BUTTON_TEXTS)
    if not button_texts:
        parser.error("至少需要一个 --button-text")
    if args.launcher_timeout <= 0 or args.main_timeout <= 0 or args.poll_interval <= 0:
        parser.error("等待参数必须大于 0")

    return LaunchConfig(
        project_root=args.project_root.expanduser().resolve(),
        launcher_path=args.launcher,
        gui_path=args.gui.expanduser().resolve(),
        launcher_title_regex=args.launcher_window_regex,
        launcher_class_regex=args.launcher_class_regex,
        main_title_regex=args.main_window_regex,
        main_class_regex=args.main_class_regex,
        launcher_timeout=args.launcher_timeout,
        main_timeout=args.main_timeout,
        poll_interval=args.poll_interval,
        button_texts=button_texts,
        resource_root=args.resource_root,
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        config = _parse_args(argv)
        run_workflow(config)
    except LaunchError as error:
        print(f"启动失败: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"启动失败: {error}", file=sys.stderr)
        return 1

    print("游戏主窗口已出现，MFAAvalonia/MXU 已启动")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
