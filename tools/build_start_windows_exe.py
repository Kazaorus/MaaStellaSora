#!/usr/bin/env python3
"""Build the Windows startup worker bundle with PyInstaller."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


APP_NAME = "start_windows"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIST_ROOT = PROJECT_ROOT / "dist"
DEFAULT_BUILD_ROOT = PROJECT_ROOT / "build" / APP_NAME


class BuildError(RuntimeError):
    """A user-actionable build failure."""


def _is_complete_resource_root(candidate: Path) -> bool:
    return all(
        (candidate / relative).is_dir()
        for relative in ("base", "windows", "base/model/ocr")
    )


def resolve_resource_root(project_root: Path, resource_root: Path | None = None) -> Path:
    candidates = []
    if resource_root is not None:
        candidates.append(resource_root.expanduser().resolve())
    candidates.extend(
        (project_root / "resource", project_root / "assets" / "resource")
    )

    for candidate in candidates:
        if _is_complete_resource_root(candidate):
            return candidate

    raise BuildError(
        "未找到完整 Maa 资源目录，需要包含 resource/base、resource/windows 和 "
        "resource/base/model/ocr"
    )


def copy_resource_tree(resource_root: Path, output_dir: Path) -> Path:
    resource_root = resource_root.expanduser().resolve()
    if not _is_complete_resource_root(resource_root):
        raise BuildError(
            "未找到完整 Maa 资源目录，需要包含 resource/base、resource/windows 和 "
            "resource/base/model/ocr"
        )
    target = output_dir / "resource"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(resource_root, target, dirs_exist_ok=True)
    return target


def build_command(
    project_root: Path,
    dist_root: Path,
    build_root: Path,
    pyinstaller_command: Sequence[str],
) -> list[str]:
    script = project_root / "start_windows.py"
    if not script.is_file():
        raise BuildError(f"未找到启动脚本: {script}")

    return [
        *pyinstaller_command,
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console",
        "--name",
        APP_NAME,
        "--distpath",
        str(dist_root),
        "--workpath",
        str(build_root),
        "--specpath",
        str(build_root),
        "--paths",
        str(project_root),
        "--collect-all",
        "maa",
        str(script),
    ]


def build_bundle(
    project_root: Path,
    dist_root: Path,
    resource_root: Path | None = None,
    *,
    build_root: Path | None = None,
    pyinstaller_command: Sequence[str] | None = None,
) -> Path:
    project_root = project_root.expanduser().resolve()
    dist_root = dist_root.expanduser().resolve()
    build_root = (build_root or project_root / "build" / APP_NAME).expanduser().resolve()
    selected_resource_root = resolve_resource_root(project_root, resource_root)
    pyinstaller_command = pyinstaller_command or (
        sys.executable,
        "-m",
        "PyInstaller",
    )
    command = build_command(
        project_root,
        dist_root,
        build_root,
        pyinstaller_command,
    )
    subprocess.run(command, cwd=project_root, check=True)

    output_dir = dist_root / APP_NAME
    executable = output_dir / f"{APP_NAME}.exe"
    if not executable.is_file():
        raise BuildError(f"PyInstaller 未生成预期 EXE: {executable}")

    copy_resource_tree(selected_resource_root, output_dir)
    return executable


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将 start_windows.py 打包为包含 MaaFramework 运行库的 Windows onedir 启动工作程序"
    )
    parser.add_argument("--resource-root", type=Path)
    parser.add_argument("--dist-root", type=Path, default=DEFAULT_DIST_ROOT)
    parser.add_argument("--build-root", type=Path, default=DEFAULT_BUILD_ROOT)
    parser.add_argument(
        "--pyinstaller",
        type=Path,
        help="可选的 PyInstaller 可执行文件；默认使用当前 Python -m PyInstaller",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    pyinstaller_command = None
    if args.pyinstaller is not None:
        pyinstaller_command = (str(args.pyinstaller.expanduser().resolve()),)

    try:
        executable = build_bundle(
            PROJECT_ROOT,
            args.dist_root,
            args.resource_root,
            build_root=args.build_root,
            pyinstaller_command=pyinstaller_command,
        )
    except (BuildError, OSError, subprocess.CalledProcessError) as error:
        print(f"EXE 打包失败: {error}", file=sys.stderr)
        return 1

    print(f"EXE 打包完成: {executable}")
    print(f"资源目录: {executable.parent / 'resource'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
