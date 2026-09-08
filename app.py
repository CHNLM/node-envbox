"""node-envbox 入口。

普通模式：启动主窗口。
提权模式：app.py --system-write <payload.json>
    以管理员身份运行，执行系统级环境变量写入后弹窗提示（供 UAC 提权链路使用）。
"""

import json
import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from node_env import core
from node_env import theme


def _app_icon_path():
    """定位程序图标 node-env.ico（打包后随 exe 分发，开发时在项目根目录）。"""
    base = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "node-env.ico")
    return path if os.path.exists(path) else ""


def _system_write(payload_file):
    with open(payload_file, "r", encoding="utf-8") as f:
        payload = json.load(f)
    node_dir = payload.get("node_dir", "")
    entries = payload.get("entries", [])
    current = core.get_path_entries("system")
    existing = {e.strip().lower() for e in current}
    added = 0
    for e in entries:
        if e and e.strip().lower() not in existing:
            current.append(e)
            added += 1
    if added:
        core.set_path_entries("system", current)
    np = os.path.join(node_dir, "node_global", "node_modules")
    if node_dir and core.get_env_var("system", "NODE_PATH") != np:
        core.set_env_var("system", "NODE_PATH", np)
    QMessageBox.information(None, "node-env",
                            f"系统级环境变量已更新：新增 {added} 条 PATH 条目，"
                            f"NODE_PATH 已设置。\n新开的终端将生效。")
    sys.exit(0)


def main():
    app = QApplication(sys.argv)
    theme.apply(app)

    if "--system-write" in sys.argv:
        idx = sys.argv.index("--system-write")
        _system_write(sys.argv[idx + 1])
        return

    from node_env.ui_main import MainWindow
    app.setApplicationName("node-env")
    app.setApplicationDisplayName("node-envbox · Node.js 环境管理")
    icon = _app_icon_path()
    if icon:
        app.setWindowIcon(QIcon(icon))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
