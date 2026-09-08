#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""node-envbox 环境搭建脚本（替代 setup.bat）。

功能：
  1. 创建虚拟环境 venv
  2. 按 requirements.txt 安装依赖 PySide6 + Nuitka + pytest

纯 Python 实现，不受 cmd/PowerShell 活动代码页(936)影响，中文输出无乱码。
用法：python scripts/setup.py
"""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
VENV_DIR = os.path.join(ROOT, "venv")
VENV_PY = os.path.join(VENV_DIR, "Scripts", "python.exe")
REQUIREMENTS = os.path.join(ROOT, "requirements.txt")
DEPS = ["-U", "pip", "-r", REQUIREMENTS]


def pause():
    """等待回车键（非交互环境自动跳过，避免 EOFError）。"""
    try:
        input("按回车键退出...")
    except EOFError:
        pass


def run(cmd, **kwargs):
    """运行命令，继承当前环境（在沙箱中运行时自动排除注入的 PYTHONPATH）。"""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)  # 防止外部 sitecustomize 干扰（如 WorkBuddy 沙箱）
    env.pop("PYTHONSTARTUP", None)
    kwargs.setdefault("env", env)
    print(f"\n>>> {' '.join(cmd)}")
    sys.stdout.flush()
    return subprocess.call(cmd, **kwargs)


def main():
    print("=" * 60)
    print(" node-envbox 环境搭建")
    print("=" * 60)

    # 步骤 1：创建 venv
    print("\n[1/2] 创建虚拟环境 venv ...")
    if os.path.exists(VENV_PY):
        print(f"  已存在：{VENV_PY}，跳过创建。")
    else:
        launcher = shutil.which("py") or shutil.which("python")
        if not launcher:
            print("[错误] 未找到 Python。请安装 Python 3.10+ 并加入 PATH 后重试。")
            pause()
            return 1
        if run([launcher, "-m", "venv", VENV_DIR]) != 0:
            print("[错误] venv 创建失败。")
            pause()
            return 1
        if not os.path.exists(VENV_PY):
            print("[错误] venv 创建失败，请确认已安装 Python 3.10+ 并加入 PATH。")
            pause()
            return 1

    # 步骤 2：安装依赖
    print(f"\n[2/2] 按 {os.path.basename(REQUIREMENTS)} 安装依赖（约 200MB，请耐心等待）...")
    if run([VENV_PY, "-m", "pip", "install"] + DEPS) != 0:
        print("[错误] 依赖安装失败，请检查网络后重试。")
        pause()
        return 1

    print("\n" + "=" * 60)
    print(" 完成！使用方式：")
    print("   启动程序 : python scripts/start.py")
    print("   打包发布 : python build.py")
    print("   运行测试 : venv\\Scripts\\python.exe -m pytest tests -q")
    print("=" * 60)
    pause()
    return 0


if __name__ == "__main__":
    sys.exit(main())
