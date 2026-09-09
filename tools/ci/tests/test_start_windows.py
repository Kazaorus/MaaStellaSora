import io
import tempfile
import unittest
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from start_windows import (
    DEFAULT_LAUNCHER_TITLE_REGEX,
    DEFAULT_MAIN_TITLE_REGEX,
    LaunchError,
    LaunchConfig,
    RuntimeBindings,
    _parse_args,
    _load_runtime,
    default_project_root,
    find_matching_window,
    main,
    run_workflow,
    wait_for_window,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def now(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += max(seconds, 0.1)


class FakeProcess:
    def __init__(self, returncode: int | None = None) -> None:
        self.returncode = returncode

    def poll(self) -> int | None:
        return self.returncode


class StartWindowsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.platform_patch = patch("start_windows.sys.platform", "win32")
        self.platform_patch.start()
        self.addCleanup(self.platform_patch.stop)

    def _make_gui(self, root: Path) -> Path:
        gui = root / "MFAAvalonia.exe"
        gui.write_text("gui", encoding="utf-8")
        return gui

    def test_default_project_root_uses_executable_directory_when_frozen(self) -> None:
        executable = Path("C:/bundle/start_windows/start_windows.exe")

        with patch.object(sys, "frozen", True, create=True), patch.object(
            sys, "executable", str(executable)
        ):
            self.assertEqual(default_project_root(), executable.parent)

    def test_runtime_uses_background_win32_input_for_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets" / "resource" / "base" / "model" / "ocr").mkdir(
                parents=True
            )
            (root / "assets" / "resource" / "windows").mkdir(parents=True)
            captured: dict[str, object] = {}

            class FakeJob:
                succeeded = True

                def wait(self):
                    return self

            class FakeResource:
                def post_bundle(self, bundle):
                    captured.setdefault("bundles", []).append(bundle)
                    return FakeJob()

            class FakeController:
                def __init__(self, *args, **kwargs):
                    captured["controller"] = (args, kwargs)

                def post_connection(self):
                    return FakeJob()

                def post_inactive(self):
                    return FakeJob()

            class FakeTasker:
                def bind(self, resource, controller):
                    captured["binding"] = (resource, controller)
                    return True

                def post_task(self, entry, override):
                    captured["task"] = (entry, override)
                    return FakeJob()

            fake_modules = {
                "maa": types.ModuleType("maa"),
                "maa.controller": types.SimpleNamespace(
                    MaaWin32InputMethodEnum=types.SimpleNamespace(
                        SendMessageWithCursorPos="background-mouse"
                    ),
                    MaaWin32ScreencapMethodEnum=types.SimpleNamespace(
                        Background="background-screencap"
                    ),
                    Win32Controller=FakeController,
                ),
                "maa.resource": types.SimpleNamespace(Resource=FakeResource),
                "maa.tasker": types.SimpleNamespace(Tasker=FakeTasker),
                "maa.toolkit": types.SimpleNamespace(Toolkit=SimpleNamespace()),
            }
            config = LaunchConfig(
                project_root=root,
                launcher_path=None,
                gui_path=root / "MFAAvalonia.exe",
                launcher_title_regex=r"launcher",
                launcher_class_regex=None,
                main_title_regex=r"xtlr",
                main_class_regex=None,
                launcher_timeout=1,
                main_timeout=1,
                poll_interval=0.1,
                button_texts=("开始游戏",),
            )

            with patch.dict(sys.modules, fake_modules):
                bindings = _load_runtime(root)
                bindings.click_launcher(SimpleNamespace(hwnd=11), config)

            args, kwargs = captured["controller"]
            self.assertEqual(args, (11,))
            self.assertEqual(kwargs["screencap_method"], "background-screencap")
            self.assertEqual(kwargs["mouse_method"], "background-mouse")
            self.assertEqual(kwargs["keyboard_method"], "background-mouse")

    def test_find_matching_window_uses_title_and_optional_class_regex(self) -> None:
        windows = [
            SimpleNamespace(hwnd=1, window_name="StellaSora Launcher", class_name="Qt5152QWindow"),
            SimpleNamespace(hwnd=2, window_name="xtlr", class_name="UnityWndClass"),
        ]

        result = find_matching_window(windows, r"launcher", r"Qt.*")

        self.assertEqual(result.hwnd, 1)
        self.assertIsNone(find_matching_window(windows, r"launcher", r"Unity.*"))

    def test_launcher_title_does_not_match_embedded_stella_sora_name(self) -> None:
        window = SimpleNamespace(
            hwnd=1,
            window_name="MaaStellaSora",
            class_name="Chrome_WidgetWin_1",
        )

        self.assertIsNone(
            find_matching_window([window], DEFAULT_LAUNCHER_TITLE_REGEX)
        )

    def test_find_matching_window_can_require_process_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = root / "launcher.exe"
            editor = root / "editor.exe"
            windows = [
                SimpleNamespace(
                    hwnd=1,
                    window_name="MaaStellaSora",
                    class_name="Chrome_WidgetWin_1",
                ),
                SimpleNamespace(
                    hwnd=2,
                    window_name="星塔旅人",
                    class_name="Chrome_WidgetWin_1",
                ),
            ]
            process_paths = {1: editor, 2: launcher}

            result = find_matching_window(
                windows,
                DEFAULT_LAUNCHER_TITLE_REGEX,
                process_path=launcher,
                process_path_getter=lambda window: process_paths[window.hwnd],
            )

        self.assertEqual(result.hwnd, 2)

    def test_wait_for_window_returns_a_window_that_appears_during_polling(self) -> None:
        clock = FakeClock()
        states = [
            [],
            [SimpleNamespace(hwnd=8, window_name="xtlr", class_name="UnityWndClass")],
        ]

        result = wait_for_window(
            lambda: states.pop(0) if states else [],
            lambda windows: find_matching_window(windows, r"xtlr", r"UnityWndClass"),
            timeout=1,
            poll_interval=0.1,
            clock=clock.now,
            sleep=clock.sleep,
        )

        self.assertEqual(result.hwnd, 8)

    def test_run_workflow_preserves_background_handoff_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = root / "launcher.exe"
            launcher.write_text("launcher", encoding="utf-8")
            gui = self._make_gui(root)

            launcher_window = SimpleNamespace(
                hwnd=11,
                window_name="StellaSora Launcher",
                class_name="LauncherClass",
                process_path=launcher,
            )
            misleading_window = SimpleNamespace(
                hwnd=10,
                window_name="StellaSora",
                class_name="LauncherClass",
                process_path=root / "editor.exe",
            )
            main_window = SimpleNamespace(
                hwnd=12,
                window_name="xtlr",
                class_name="UnityWndClass",
            )
            states = [[], [], [misleading_window, launcher_window], [main_window]]
            events: list[str] = []
            started_commands: list[list[str]] = []
            started_calls: list[tuple[list[str], dict[str, object]]] = []
            clock = FakeClock()

            def find_windows():
                return states.pop(0) if states else [main_window]

            def start_process(command, **_kwargs):
                started_commands.append(command)
                started_calls.append((command, _kwargs))
                events.append("start:" + Path(command[0]).name)
                return FakeProcess()

            def click_launcher(window, _config):
                self.assertEqual(window.hwnd, 11)
                events.append("click-background")

            config = LaunchConfig(
                project_root=root,
                launcher_path=launcher,
                gui_path=gui,
                launcher_title_regex=r"launcher",
                launcher_class_regex=r"LauncherClass",
                main_title_regex=r"xtlr",
                main_class_regex=r"UnityWndClass",
                launcher_timeout=1,
                main_timeout=1,
                poll_interval=0.1,
                button_texts=("开始游戏",),
            )
            bindings = RuntimeBindings(
                initialize=lambda _root: None,
                find_windows=find_windows,
                click_launcher=click_launcher,
            )

            with patch(
                "start_windows._get_window_process_path",
                side_effect=lambda window: window.process_path,
            ):
                run_workflow(
                    config,
                    bindings=bindings,
                    start_process=start_process,
                    clock=clock.now,
                    sleep=clock.sleep,
                )

            self.assertEqual(
                events,
                [
                    "start:launcher.exe",
                    "click-background",
                    "start:MFAAvalonia.exe",
                ],
            )
            self.assertEqual(
                started_commands,
                [[str(launcher)], [str(gui.resolve())]],
            )
            self.assertEqual(started_calls[-1][1]["cwd"], str(gui.parent))
            self.assertFalse(started_calls[-1][1]["shell"])

    def test_run_workflow_skips_launcher_when_main_window_already_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main_window = SimpleNamespace(
                hwnd=12,
                window_name="xtlr",
                class_name="UnityWndClass",
            )
            gui = self._make_gui(root)
            started_commands: list[list[str]] = []

            config = LaunchConfig(
                project_root=root,
                launcher_path=None,
                gui_path=gui,
                launcher_title_regex=r"launcher",
                launcher_class_regex=None,
                main_title_regex=r"xtlr",
                main_class_regex=r"UnityWndClass",
                launcher_timeout=1,
                main_timeout=1,
                poll_interval=0.1,
                button_texts=("开始游戏",),
            )
            bindings = RuntimeBindings(
                initialize=lambda _root: None,
                find_windows=lambda: [main_window],
                click_launcher=lambda _window, _config: self.fail(
                    "launcher should not be clicked"
                ),
            )

            run_workflow(
                config,
                bindings=bindings,
                start_process=lambda command, **_kwargs: (
                    started_commands.append(command),
                    FakeProcess(),
                )[1],
            )

            self.assertEqual(started_commands, [[str(gui.resolve())]])

    def test_default_main_title_regex_matches_all_supported_server_titles(self) -> None:
        for title in ("xtlr", "星塔旅人", "ステラソラ", "StellaSora"):
            with self.subTest(title=title):
                window = SimpleNamespace(
                    hwnd=12,
                    window_name=title,
                    class_name="UnityWndClass",
                )
                self.assertIsNotNone(
                    find_matching_window(
                        [window], DEFAULT_MAIN_TITLE_REGEX, r"UnityWndClass"
                    )
                )

    def test_parse_args_requires_gui_path(self) -> None:
        with self.assertRaises(SystemExit):
            _parse_args(["--launcher", "C:/launcher.exe"])

    def test_main_converts_unexpected_exception_to_failure(self) -> None:
        stderr = io.StringIO()
        with patch(
            "start_windows._parse_args",
            return_value=SimpleNamespace(),
        ), patch(
            "start_windows.run_workflow",
            side_effect=RuntimeError("unexpected failure"),
        ), patch("start_windows.sys.stderr", stderr):
            result = main([])

        self.assertEqual(result, 1)
        self.assertIn("启动失败: unexpected failure", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_run_workflow_rejects_missing_gui(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = LaunchConfig(
                project_root=root,
                launcher_path=None,
                gui_path=root / "missing.exe",
                launcher_title_regex=r"launcher",
                launcher_class_regex=None,
                main_title_regex=r"xtlr",
                main_class_regex=None,
                launcher_timeout=1,
                main_timeout=1,
                poll_interval=0.1,
                button_texts=("开始游戏",),
            )
            bindings = RuntimeBindings(
                initialize=lambda _root: None,
                find_windows=lambda: [
                    SimpleNamespace(
                        hwnd=12,
                        window_name="xtlr",
                        class_name="UnityWndClass",
                    )
                ],
                click_launcher=lambda _window, _config: self.fail(
                    "launcher should not be clicked"
                ),
            )

            with self.assertRaisesRegex(LaunchError, "MFAAvalonia/MXU"):
                run_workflow(config, bindings=bindings)

    def test_run_workflow_validates_gui_before_starting_game(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = root / "launcher.exe"
            launcher.write_text("launcher", encoding="utf-8")
            config = LaunchConfig(
                project_root=root,
                launcher_path=launcher,
                gui_path=root / "missing.exe",
                launcher_title_regex=r"launcher",
                launcher_class_regex=None,
                main_title_regex=r"xtlr",
                main_class_regex=None,
                launcher_timeout=0.1,
                main_timeout=0.1,
                poll_interval=0.1,
                button_texts=("开始游戏",),
            )
            bindings = RuntimeBindings(
                initialize=lambda _root: None,
                find_windows=lambda: [],
                click_launcher=lambda _window, _config: self.fail(
                    "launcher click should not be reached"
                ),
            )
            started_commands: list[list[str]] = []
            clock = FakeClock()

            with self.assertRaisesRegex(LaunchError, "MFAAvalonia/MXU"):
                run_workflow(
                    config,
                    bindings=bindings,
                    start_process=lambda command, **_kwargs: (
                        started_commands.append(command),
                        FakeProcess(),
                    )[1],
                    clock=clock.now,
                    sleep=clock.sleep,
                )

            self.assertEqual(started_commands, [])

    def test_run_workflow_translates_launcher_start_oserror(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = root / "launcher.exe"
            launcher.write_text("launcher", encoding="utf-8")
            gui = self._make_gui(root)
            config = LaunchConfig(
                project_root=root,
                launcher_path=launcher,
                gui_path=gui,
                launcher_title_regex=r"launcher",
                launcher_class_regex=None,
                main_title_regex=r"xtlr",
                main_class_regex=None,
                launcher_timeout=1,
                main_timeout=1,
                poll_interval=0.1,
                button_texts=("开始游戏",),
            )
            bindings = RuntimeBindings(
                initialize=lambda _root: None,
                find_windows=lambda: [],
                click_launcher=lambda _window, _config: self.fail(
                    "launcher click should not be reached"
                ),
            )

            def fail_start(_command, **_kwargs):
                raise OSError("permission denied")

            with self.assertRaisesRegex(LaunchError, "启动游戏启动器失败"):
                run_workflow(config, bindings=bindings, start_process=fail_start)

    def test_run_workflow_translates_gui_start_oserror(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gui = self._make_gui(root)
            main_window = SimpleNamespace(
                hwnd=12,
                window_name="xtlr",
                class_name="UnityWndClass",
            )
            config = LaunchConfig(
                project_root=root,
                launcher_path=None,
                gui_path=gui,
                launcher_title_regex=r"launcher",
                launcher_class_regex=None,
                main_title_regex=r"xtlr",
                main_class_regex=None,
                launcher_timeout=1,
                main_timeout=1,
                poll_interval=0.1,
                button_texts=("开始游戏",),
            )
            bindings = RuntimeBindings(
                initialize=lambda _root: None,
                find_windows=lambda: [main_window],
                click_launcher=lambda _window, _config: self.fail(
                    "launcher should not be clicked"
                ),
            )

            def fail_start(_command, **_kwargs):
                raise OSError("permission denied")

            with self.assertRaisesRegex(LaunchError, "启动MFAAvalonia/MXU失败"):
                run_workflow(config, bindings=bindings, start_process=fail_start)

    def test_run_workflow_rejects_gui_that_exits_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gui = self._make_gui(root)
            main_window = SimpleNamespace(
                hwnd=12,
                window_name="xtlr",
                class_name="UnityWndClass",
            )
            config = LaunchConfig(
                project_root=root,
                launcher_path=None,
                gui_path=gui,
                launcher_title_regex=r"launcher",
                launcher_class_regex=None,
                main_title_regex=r"xtlr",
                main_class_regex=None,
                launcher_timeout=1,
                main_timeout=1,
                poll_interval=0.1,
                button_texts=("开始游戏",),
            )
            bindings = RuntimeBindings(
                initialize=lambda _root: None,
                find_windows=lambda: [main_window],
                click_launcher=lambda _window, _config: self.fail(
                    "launcher should not be clicked"
                ),
            )

            with self.assertRaisesRegex(LaunchError, "MFAAvalonia/MXU启动后立即退出"):
                run_workflow(
                    config,
                    bindings=bindings,
                    start_process=lambda _command, **_kwargs: FakeProcess(1),
                )


if __name__ == "__main__":
    unittest.main()
