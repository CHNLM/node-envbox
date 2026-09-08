#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""node-envbox 启动脚本（替代 start.bat）。

以 pythonw 无控制台方式后台启动 app.py，启动后本脚本立即退出。
纯 Python 实现，不受 cmd/PowerShell 活动代码页(936)影响。
用法：python scripts/start.py
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录
APP = os.path.join(ROOT, "app.py")

DETACHED_PROCESS = 0x00000008  # Windows: 不继承本进程控制台


def pythonw_path():
    """定位 pythonw.exe：优先 .venv（uv 约定），回退到 venv（setup.py 约定）。"""
    for name in (".venv", "venv"):
        p = os.path.join(ROOT, name, "Scripts", "pythonw.exe")
        if os.path.exists(p):
            return p
    return os.path.join(ROOT, "venv", "Scripts", "pythonw.exe")


def pause():
    """等待回车键（非交互环境自动跳过，避免 EOFError）。"""
    try:
        input("按回车键退出...")
    except EOFError:
        pass


def main():
    PYTHONW = pythonw_path()
    if not os.path.exists(PYTHONW):
        print("[错误] 未找到虚拟环境（.venv 或 venv），请先运行 setup.py"
              "（python scripts/setup.py）或 uv 创建环境。")
        pause()
        return 1
    if not os.path.exists(APP):
        print(f"[错误] 未找到入口脚本：{APP}")
        pause()
        return 1

    print("正在启动 node-envbox GUI ...")
    sys.stdout.flush()
    try:
        subprocess.Popen(
            [PYTHONW, APP],
            cwd=ROOT,
            creationflags=DETACHED_PROCESS,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as e:
        print(f"[错误] 启动失败：{e}")
        pause()
        return 1
    print("已启动。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
