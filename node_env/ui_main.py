"""主窗口与全部功能页签。

页签：概览 / 初始化配置 / 镜像源 / 全局包 / 环境变量 / 备份回滚 / 验证中心
所有耗时操作通过 TaskRunner 进入后台线程，日志经 bus.log 实时推送。
"""

import json
import os
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QStackedWidget, QTableWidget,
    QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from . import config as cfg_mod
from . import core
from . import envs
from .runner import TaskRunner, bus
from .theme import COLORS as C

LOG_COLORS = {"info": C["info"], "ok": C["ok"], "warn": C["warn"], "error": C["error"]}


def _btn(text, slot, tip="", kind="default"):
    """创建按钮；kind: default / primary（抹茶绿主操作）/ danger（暖红危险操作）。"""
    b = QPushButton(text)
    if slot:
        b.clicked.connect(slot)
    if tip:
        b.setToolTip(tip)
    if kind != "default":
        b.setProperty("kind", kind)
        b.style().unpolish(b)
        b.style().polish(b)
    return b


def _label(text="", bold=False, color=None, wrap=True, size=None):
    l = QLabel(text)
    style = []
    if bold:
        style.append("font-weight:600;")
    if color:
        style.append(f"color:{color};")
    if size:
        style.append(f"font-size:{size}px;")
    if style:
        l.setStyleSheet("".join(style))
    if wrap:
        l.setWordWrap(True)
    return l


class LogPanel(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(2000)

    @staticmethod
    def _fmt_ts():
        """真实系统时间戳（本地时钟，非程序启动相对计时）。"""
        return time.strftime("[%Y-%m-%d %H:%M:%S]")

    def append_line(self, text, level="info"):
        color = LOG_COLORS.get(level, C["info"])
        ts = self._fmt_ts()
        self.appendHtml(f"<span style='color:{C['text_sub']};'>{ts} </span>"
                        f"<span style='color:{color};'>{text}</span>")


# ---------------------------------------------------------------------------
# 概览页
# ---------------------------------------------------------------------------

class OverviewPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)

        # 标题
        lay.addWidget(_label("环境概览", bold=True, size=20))

        # 环境切换行
        top = QHBoxLayout()
        self.env_combo = QComboBox()
        self.env_combo.setMinimumWidth(430)
        self.env_combo.setToolTip("切换当前生效的 Node 环境，所有页签将跟随")
        self.env_combo.currentIndexChanged.connect(self._on_env_changed)
        top.addWidget(self.env_combo, 1)
        top.addWidget(_btn("重新检测", self.rescan,
                           tip="重新扫描系统 PATH 与常见目录，发现新的 Node 环境"))
        top.addWidget(_btn("添加便携环境", self.add_portable,
                           tip="手动指定便携解压版 / 项目内嵌的 Node 目录"))
        lay.addLayout(top)

        self.env_info = _label("")
        lay.addWidget(self.env_info)

        self.cards = {}
        grid = QGridLayout()
        for i, (key, title) in enumerate([
                ("node", "Node 版本"), ("npm", "npm 版本"),
                ("registry", "当前镜像源"), ("pkgs", "全局包数")]):
            card = QWidget()
            card.setObjectName("card")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 14, 16, 16)
            cl.setSpacing(4)
            cl.addWidget(_label(title, color=C["text_sub"], size=16))
            val = _label("—", bold=True, size=24)
            cl.addWidget(val)
            self.cards[key] = val
            grid.addWidget(card, i // 2, i % 2)
        lay.addLayout(grid)
        btns = QHBoxLayout()
        btns.addWidget(_btn("立即检测", self.detect, kind="primary"))
        btns.addStretch(1)
        lay.addLayout(btns)
        self.report = _label("", color=C["text_sub"])
        lay.addWidget(self.report)
        lay.addStretch(1)
        self.runner = TaskRunner(on_done=self._on_detect)
        self.refresh_envs()

    # ---------- 环境切换 ----------
    def refresh_envs(self):
        """用配置中的环境列表重建下拉框，保持当前选中。"""
        self.env_combo.blockSignals(True)
        self.env_combo.clear()
        for e in self.win.cfg.get("environments", []):
            label = e["name"] + ("  ·  " + e["dir"] if e["dir"] else "  ·  未指定目录")
            self.env_combo.addItem(label, e["id"])
        idx = next((i for i in range(self.env_combo.count())
                    if self.env_combo.itemData(i) == self.win.cfg.get("active_env")), 0)
        self.env_combo.setCurrentIndex(idx)
        self.env_combo.blockSignals(False)
        self._update_env_info()

    def _on_env_changed(self, idx):
        eid = self.env_combo.itemData(idx)
        if eid and eid != self.win.cfg.get("active_env"):
            self.win.cfg["active_env"] = eid
            self.win.save_cfg()
            self.win.current_env = envs.pick_active(self.win.cfg)
            bus.log.emit(f"[环境] 已切换到 {self.win.current_env['name']}"
                         f"（{self.win.current_env['dir'] or '未指定目录'}）", "ok")
            self.win.update_statusbar()
        self._update_env_info()
        self.detect()

    def _update_env_info(self):
        e = self.win.current_env
        if not e or not e.get("dir"):
            self.env_info.setText("当前环境未指定 Node 目录，请「添加便携环境」或「重新检测」。")
            self.env_info.setStyleSheet(f"color:{C['warn']};font-weight:600;")
            return
        kind_txt = envs.KIND_LABEL.get(e.get("kind", ""), e.get("kind", ""))
        self.env_info.setText(f"当前环境：{e['name']}  ·  类型：{kind_txt}  ·  目录：{e['dir']}")
        self.env_info.setStyleSheet("")

    def rescan(self):
        auto_dirs = core.detect_node_dirs()
        added = envs.merge_auto(self.win.cfg, auto_dirs)
        envs.ensure_initialized(self.win.cfg, auto_dirs)
        self.win.save_cfg()
        self.win.current_env = envs.pick_active(self.win.cfg)
        self.refresh_envs()
        bus.log.emit(f"[环境] 重新检测完成：共 {len(auto_dirs)} 个自动发现，"
                     f"新增 {added} 个环境", "ok" if added else "info")
        self.detect()

    def add_portable(self):
        d = QFileDialog.getExistingDirectory(self, "选择 Node.js 安装目录（便携/项目环境）")
        if not d:
            return
        if not os.path.isfile(os.path.join(d, "node.exe")):
            QMessageBox.warning(self, "提示", "所选目录中未找到 node.exe")
            return
        env = envs.add_environment(self.win.cfg, d)
        if env is None:
            QMessageBox.warning(self, "提示", "添加失败：目录不可用")
            return
        self.win.cfg["active_env"] = env["id"]
        self.win.save_cfg()
        self.win.current_env = envs.pick_active(self.win.cfg)
        self.refresh_envs()
        bus.log.emit(f"[环境] 已添加便携环境：{env['name']}", "ok")
        self.detect()

    # ---------- 检测 ----------
    def detect(self):
        node_dir = self.win.node_dir
        if not node_dir:
            self.report.setText("未检测到 Node 安装目录，请手动指定。")
            return
        self.report.setText("检测中…")
        self.runner.run(self._collect, node_dir)

    @staticmethod
    def _collect(node_dir):
        """在后台线程采集概览数据（含会触发的 npm 子进程调用，避免主线程卡顿）。"""
        data = core.env_probe(node_dir)
        prefix = core.npm_config_get(node_dir, "prefix")
        cache = core.npm_config_get(node_dir, "cache")
        data["detail"] = (f"目录：{node_dir or '—'}\n"
                          f"prefix：{prefix or '—'}\n"
                          f"cache：{cache or '—'}\n"
                          f"管理员权限：{'是' if core.is_admin() else '否'}")
        return data

    def _on_detect(self, data):
        self.cards["node"].setText(data["node"])
        self.cards["npm"].setText(data["npm"])
        self.cards["registry"].setText(data["registry"])
        self.cards["pkgs"].setText(data["pkgs"])
        self.report.setText(data.get("detail", ""))
        self.win.update_statusbar()


# ---------------------------------------------------------------------------
# 初始化配置页
# ---------------------------------------------------------------------------

class SetupPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.addWidget(_label("初始化与 npm 配置", bold=True, size=20))
        lay.addWidget(_label("一键完成：创建 node_global / node_cache / node_modules，"
                             "并把 prefix、cache 指向它们。", color=C["text_sub"]))
        btns = QHBoxLayout()
        btns.addWidget(_btn("初始化目录", self.init_dirs, kind="primary"))
        btns.addWidget(_btn("配置 npm（prefix/cache）", self.set_npm))
        btns.addWidget(_btn("校验配置", self.verify_cfg))
        lay.addLayout(btns)
        self.status = _label("")
        lay.addWidget(self.status)
        lay.addStretch(1)
        self.runner = TaskRunner(on_done=lambda r: self.status.setText(r or "完成 ✓"))

    def _log(self, text, level="info"):
        bus.log.emit(text, level)

    def init_dirs(self):
        if not self.win.node_dir:
            self._log("[初始化] 未指定 Node 目录，请先添加/检测环境", "warn")
            return
        self.runner.run(self._init, self.win.node_dir)

    @staticmethod
    def _init(node_dir):
        created, skipped = [], []
        for d in ("node_global", "node_cache", "node_modules"):
            p = os.path.join(node_dir, d)
            if os.path.isdir(p):
                skipped.append(d)
            else:
                os.makedirs(p, exist_ok=True)
                created.append(d)
        return f"已创建：{'、'.join(created) or '无'}；已存在跳过：{'、'.join(skipped) or '无'}"

    def set_npm(self):
        if not self.win.node_dir:
            self._log("[初始化] 未指定 Node 目录，请先添加/检测环境", "warn")
            return

        def _do(node_dir):
            core.npm_config_set(node_dir, "prefix", os.path.join(node_dir, "node_global"),
                                self._log)
            core.npm_config_set(node_dir, "cache", os.path.join(node_dir, "node_cache"),
                                self._log)
            return "npm 配置完成"
        self.runner.run(_do, self.win.node_dir)

    def verify_cfg(self):
        if not self.win.node_dir:
            self._log("[初始化] 未指定 Node 目录，请先添加/检测环境", "warn")
            return

        def _do(node_dir):
            p = core.npm_config_get(node_dir, "prefix")
            c = core.npm_config_get(node_dir, "cache")
            r = core.npm_config_get(node_dir, "registry")
            exp_p = os.path.join(node_dir, "node_global")
            exp_c = os.path.join(node_dir, "node_cache")
            ok_p = p.lower() == exp_p.lower()
            ok_c = c.lower() == exp_c.lower()
            self._log(f"[校验] prefix = {p}  {'OK' if ok_p else '（应为 ' + exp_p + '）'}",
                      "ok" if ok_p else "warn")
            self._log(f"[校验] cache  = {c}  {'OK' if ok_c else '（应为 ' + exp_c + '）'}",
                      "ok" if ok_c else "warn")
            self._log(f"[校验] registry = {r}", "info")
            return "校验完成"
        self.runner.run(_do, self.win.node_dir)


# ---------------------------------------------------------------------------
# 镜像源页
# ---------------------------------------------------------------------------

class MirrorsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.current_registry = ""
        lay = QVBoxLayout(self)
        lay.addWidget(_label("镜像源管理", bold=True, size=20))
        lay.addWidget(_label("源链接变动时，直接在表格中修改 URL 保存即可；"
                             "「设为当前」一键切换 npm registry。", color=C["text_sub"]))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["名称", "URL", "连通状态", "当前"])
        header = self.table.horizontalHeader()
        header.setTextElideMode(Qt.ElideMiddle)
        self.table.setColumnWidth(0, 100)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 50)
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # URL 列弹性，其余固定
        lay.addWidget(self.table)
        btns = QHBoxLayout()
        btns.addWidget(_btn("新增", self.add_mirror))
        btns.addWidget(_btn("编辑", self.edit_mirror))
        btns.addWidget(_btn("删除", self.del_mirror, kind="danger"))
        btns.addWidget(_btn("设为当前", self.set_current, kind="primary"))
        btns.addWidget(_btn("测试全部连接", self.ping_all))
        lay.addLayout(btns)
        self.auto = QCheckBox("启动/切换后自动检测连通性")
        self.auto.setChecked(True)
        self.auto.stateChanged.connect(self._on_auto_toggled)
        lay.addWidget(self.auto)
        lay.addStretch(1)
        self.runner = TaskRunner(on_done=self._on_ping)
        self.switch_runner = TaskRunner(on_done=self._on_switched)
        self.refresh()
        # 启动时按勾选状态自动 ping 一次（增删改等 refresh 不再重复触发）
        if self.auto.isChecked():
            self.ping_all()

    def _on_auto_toggled(self, state):
        if state and self.win.node_dir:
            self.ping_all()
        self.refresh()

    # ---- 数据 ----
    def refresh(self):
        node_dir = self.win.node_dir
        if not node_dir:
            self.table.setRowCount(0)
            return
        self.current_registry = core.npm_config_get(node_dir, "registry")
        self.table.setRowCount(0)
        for m in self.win.cfg["mirrors"]:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(m["name"]))
            self.table.setItem(r, 1, QTableWidgetItem(m["url"]))
            cur = "✓" if m["url"].strip("/").lower() == self.current_registry.strip("/").lower() else ""
            self.table.setItem(r, 3, QTableWidgetItem(cur))
            st = QTableWidgetItem("待检测")
            st.setForeground(QColor(C["text_sub"]))
            self.table.setItem(r, 2, st)

    def _save(self):
        self.win.save_cfg()

    # ---- 增删改 ----
    def add_mirror(self):
        name, ok1 = QInputDialog.getText(self, "新增镜像源", "名称：")
        if not ok1 or not name.strip():
            return
        url, ok2 = QInputDialog.getText(self, "新增镜像源", "URL（http/https）：")
        if not ok2 or not url.strip().startswith(("http://", "https://")):
            QMessageBox.warning(self, "提示", "URL 必须以 http:// 或 https:// 开头")
            return
        self.win.cfg["mirrors"].append({"name": name.strip(), "url": url.strip()})
        self._save()
        bus.log.emit(f"[镜像源] 已新增 {name.strip()}", "ok")
        self.refresh()

    def _selected(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self.win.cfg["mirrors"]):
            QMessageBox.information(self, "提示", "请先选中一行")
            return None
        return r

    def edit_mirror(self):
        r = self._selected()
        if r is None:
            return
        m = self.win.cfg["mirrors"][r]
        url, ok = QInputDialog.getText(self, "编辑镜像源", "URL：", text=m["url"])
        if ok and url.strip().startswith(("http://", "https://")):
            self.win.cfg["mirrors"][r]["url"] = url.strip()
            self._save()
            bus.log.emit(f"[镜像源] 已更新 {m['name']} → {url.strip()}", "ok")
            self.refresh()

    def del_mirror(self):
        r = self._selected()
        if r is None:
            return
        m = self.win.cfg["mirrors"][r]
        if QMessageBox.question(self, "确认", f"删除镜像源「{m['name']}」？") != QMessageBox.Yes:
            return
        self.win.cfg["mirrors"].pop(r)
        self._save()
        bus.log.emit(f"[镜像源] 已删除 {m['name']}", "warn")
        self.refresh()

    # ---- 设为当前 ----
    def set_current(self):
        r = self._selected()
        if r is None:
            return
        m = self.win.cfg["mirrors"][r]

        def _do(node_dir, url, name):
            ok = core.set_registry(node_dir, url, lambda t, l="info": bus.log.emit(t, l))
            if ok:
                got = core.npm_config_get(node_dir, "registry")
                return f"已切换为 {name}（校验：{got}）"
            return "切换失败"
        self.switch_runner.run(_do, self.win.node_dir, m["url"], m["name"])

    def _on_switched(self, msg):
        bus.log.emit(f"[镜像源] {msg}", "ok" if msg.startswith("已切换") else "error")
        self.win.update_statusbar()
        self.refresh()

    # ---- 连通性 ----
    def ping_all(self):
        if self.runner.is_running():
            return
        urls = [(i, m["url"]) for i, m in enumerate(self.win.cfg["mirrors"])]
        timeout = int(self.win.cfg["settings"].get("ping_timeout", 5))
        self.runner.run(self._ping_worker, urls, timeout)

    @staticmethod
    def _ping_worker(urls, timeout):
        return [(i, *core.ping_url(u, timeout)) for i, u in urls]

    def _on_ping(self, results):
        ok_cnt = 0
        for i, ok, desc in results:
            if i >= self.table.rowCount():
                continue
            if ok:
                ok_cnt += 1
            item = QTableWidgetItem(("可用 · " if ok else "不可达 · ") + desc)
            item.setForeground(QColor(C["ok"] if ok else C["error"]))
            self.table.setItem(i, 2, item)
        bus.log.emit(f"[镜像源] 连通性检测完成：{ok_cnt}/{len(results)} 可用",
                     "ok" if ok_cnt else "warn")


# ---------------------------------------------------------------------------
# 全局包页
# ---------------------------------------------------------------------------

class PackagesPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.addWidget(_label("全局包管理", bold=True, size=20))
        btns = QHBoxLayout()
        btns.addWidget(_btn("刷新列表", self.refresh))
        btns.addWidget(_btn("卸载所选", self.uninstall, kind="danger"))
        btns.addWidget(_btn("npm cache 清理", self.clean_cache, kind="danger"))
        btns.addStretch(1)
        lay.addLayout(btns)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["包名", "版本"])
        self.table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.table)
        self.size_lab = _label("")
        lay.addWidget(self.size_lab)
        lay.addStretch(1)
        self.runner = TaskRunner(on_done=self._on_loaded)
        self.mut_runner = TaskRunner(on_done=lambda r: self.refresh())
        self.refresh()

    def refresh(self):
        node_dir = self.win.node_dir
        if not node_dir:
            self.table.setRowCount(0)
            self.size_lab.setText("未指定 Node 目录")
            return

        def _do(node_dir):
            pkgs = core.list_global_packages(node_dir)
            g = os.path.join(node_dir, "node_global")
            c = os.path.join(node_dir, "node_cache")
            size = (f"node_global 占用 {core.dir_size(g) / 1048576:.1f} MB · "
                    f"node_cache 占用 {core.dir_size(c) / 1048576:.1f} MB")
            return pkgs, size
        self.runner.run(_do, self.win.node_dir)

    def _on_loaded(self, result):
        pkgs, size = result
        self.table.setRowCount(0)
        for name, ver in pkgs:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(name))
            self.table.setItem(r, 1, QTableWidgetItem(ver))
        self.size_lab.setText(size)

    def uninstall(self):
        r = self.table.currentRow()
        if r < 0:
            QMessageBox.information(self, "提示", "请先选择要卸载的包")
            return
        name = self.table.item(r, 0).text()
        if QMessageBox.question(self, "确认", f"卸载全局包 {name}？") != QMessageBox.Yes:
            return
        self.mut_runner.run(core.uninstall_global, self.win.node_dir, name,
                            lambda t, l="info": bus.log.emit(t, l))

    def clean_cache(self):
        self.mut_runner.run(core.cache_clean, self.win.node_dir,
                            lambda t, l="info": bus.log.emit(t, l))


# ---------------------------------------------------------------------------
# 环境变量页
# ---------------------------------------------------------------------------

class EnvVarsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.addWidget(_label("环境变量（用户级）", bold=True, size=20))
        self.admin_lab = _label("")
        lay.addWidget(self.admin_lab)
        self.env_lab = _label("")
        lay.addWidget(self.env_lab)
        self.path_list = QListWidget()
        lay.addWidget(self.path_list)
        row = QHBoxLayout()
        self.new_path = QLineEdit()
        self.new_path.setPlaceholderText("输入要追加的 PATH 条目，如 D:\\node")
        row.addWidget(self.new_path)
        row.addWidget(_btn("追加", self.add_entry))
        row.addWidget(_btn("移除所选", self.remove_entry, kind="danger"))
        lay.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(_btn("一键追加 Node 目录", self.fix_path))
        row2.addWidget(_btn("设置 NODE_PATH", self.set_node_path))
        self.sys_btn = _btn("写入系统级 PATH（需管理员）", self.system_write, kind="primary")
        row2.addWidget(self.sys_btn)
        row2.addStretch(1)
        lay.addLayout(row2)
        lay.addWidget(_label("说明：系统级 PATH 影响所有用户与服务；个人开发机建议只用用户级，"
                             "系统级仅在有服务/多账户需求时启用。", color=C["text_sub"]))
        lay.addStretch(1)
        self.runner = TaskRunner(on_done=lambda r: self.refresh())
        self.refresh()

    def refresh(self):
        self.admin_lab.setText("当前进程权限：" + ("管理员" if core.is_admin() else "普通用户"))
        e = self.win.current_env or {}
        if e.get("dir"):
            kind_txt = envs.KIND_LABEL.get(e.get("kind", ""), e.get("kind", ""))
            self.env_lab.setText(f"当前环境：{e['name']}（{kind_txt}）· 目录 {e['dir']}"
                                 + ("（便携/项目环境将前置写入 PATH）"
                                    if e.get("kind") in ("portable", "project") else ""))
            self.env_lab.setStyleSheet(f"color:{C['text_sub']};")
        else:
            self.env_lab.setText("当前环境未指定目录，请先在「概览」页添加环境")
            self.env_lab.setStyleSheet(f"color:{C['warn']};font-weight:600;")
        self.sys_btn.setEnabled(True)
        self.path_list.clear()
        for entry in core.get_path_entries("user"):
            QListWidgetItem(entry, self.path_list)
        np = core.get_env_var("user", "NODE_PATH")
        self.path_list.addItem("")  # 分隔视觉
        self.path_list.addItem(f"NODE_PATH = {np or '未设置'}")
        sys_entries = core.get_path_entries("system")
        self.path_list.addItem("")
        self.path_list.addItem(f"系统级 PATH 共 {len(sys_entries)} 条（只读展示，前 3 条："
                               + " ; ".join(sys_entries[:3]) + " …)")

    def add_entry(self):
        e = self.new_path.text().strip()
        if not e:
            return
        def _do(node_dir, entry):
            core.backup_before_mutate(node_dir, "env user path")
            entries = core.get_path_entries("user")
            if entry not in entries:
                entries.append(entry)
                core.set_path_entries("user", entries,
                                      lambda t, l="info": bus.log.emit(t, l))
            else:
                bus.log.emit("[环境变量] 该条目已存在", "info")
            return True
        self.runner.run(_do, self.win.node_dir, e)
        self.new_path.clear()

    def remove_entry(self):
        item = self.path_list.currentItem()
        if not item or not item.text().strip():
            return
        entry = item.text().strip()
        if entry.startswith("NODE_PATH") or entry.startswith("系统级") or entry == "":
            return
        def _do(node_dir, e):
            core.backup_before_mutate(node_dir, "env user path")
            entries = [x for x in core.get_path_entries("user") if x != e]
            core.set_path_entries("user", entries,
                                  lambda t, l="info": bus.log.emit(t, l))
            bus.log.emit(f"[环境变量] 已移除 PATH 条目：{e}", "warn")
            return True
        self.runner.run(_do, self.win.node_dir, entry)

    def fix_path(self):
        e = self.win.current_env or {}
        if not self.win.node_dir:
            self._no_node()
            return
        prepend = e.get("kind") in ("portable", "project")
        self.runner.run(core.add_user_path_entries, self.win.node_dir,
                        lambda t, l="info": bus.log.emit(t, l), prepend)

    def set_node_path(self):
        if not self.win.node_dir:
            self._no_node()
            return

        def _do(node_dir):
            np = os.path.join(node_dir, "node_global", "node_modules")
            core.backup_before_mutate(node_dir, "env user NODE_PATH")
            core.set_env_var("user", "NODE_PATH", np,
                             lambda t, l="info": bus.log.emit(t, l))
            return True
        self.runner.run(_do, self.win.node_dir)

    def _no_node(self):
        """无 Node 目录时的统一提示。"""
        bus.log.emit("[环境变量] 未指定 Node 目录，请先添加/检测环境", "warn")

    def system_write(self):
        """提权写入系统级 PATH：生成载荷 -> runas 重启自身执行。"""
        node_dir = self.win.node_dir
        if not node_dir:
            self._no_node()
            return
        payload = {"node_dir": node_dir,
                   "entries": [node_dir, os.path.join(node_dir, "node_global")]}
        os.makedirs(core.backup_dir(node_dir), exist_ok=True)
        pf = os.path.join(core.backup_dir(node_dir), "system_write.json")
        with open(pf, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        import sys
        import ctypes
        script = os.path.abspath(sys.argv[0])
        args = f'"{script}" --system-write "{pf}"'
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable,
                                                  args, None, 1)
        if ret <= 32:
            QMessageBox.warning(self, "提示", "提权被取消或失败")
        bus.log.emit("[环境变量] 已触发系统级写入（UAC），完成后请查看结果", "info")


# ---------------------------------------------------------------------------
# 备份回滚页
# ---------------------------------------------------------------------------

class BackupPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.addWidget(_label("配置备份与回滚", bold=True, size=20))
        btns = QHBoxLayout()
        btns.addWidget(_btn("立即备份", self.backup_now, kind="primary"))
        btns.addWidget(_btn("还原所选快照", self.restore, kind="danger"))
        btns.addWidget(_btn("刷新", self.refresh))
        btns.addStretch(1)
        lay.addLayout(btns)
        self.list = QListWidget()
        lay.addWidget(self.list)
        lay.addWidget(_label("操作历史（最近 100 条）", bold=True))
        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        self.history.setMaximumHeight(140)
        lay.addWidget(self.history)
        self.runner = TaskRunner(on_done=lambda r: self.refresh())
        self.refresh()

    def refresh(self):
        self.list.clear()
        node_dir = self.win.node_dir
        snaps = core.list_backups(node_dir) if node_dir else []
        for snap in snaps:
            mani = os.path.join(snap, "manifest.json")
            reason = ""
            try:
                with open(mani, "r", encoding="utf-8") as f:
                    reason = json.load(f).get("reason", "")
            except Exception:
                pass
            QListWidgetItem(f"{os.path.basename(snap)}  （{reason}）", self.list)
        recs = core.list_history(node_dir, 100) if node_dir else []
        self.history.setPlainText("\n".join(
            f"[{r.get('ts')}] {r.get('action')} {'✓' if r.get('ok') else '✗'} {r.get('detail','')}"
            for r in reversed(recs)))

    def backup_now(self):
        self.runner.run(core.create_backup, self.win.node_dir, "manual",
                        lambda t, l="info": bus.log.emit(t, l))

    def restore(self):
        i = self.list.currentRow()
        snaps = core.list_backups(self.win.node_dir)
        if i < 0 or i >= len(snaps):
            QMessageBox.information(self, "提示", "请先选择要还原的快照")
            return
        snap = snaps[i]
        if QMessageBox.question(self, "确认还原",
                                f"将从快照还原 .npmrc / 用户环境变量 / 配置，继续？\n{snap}"
                                ) != QMessageBox.Yes:
            return
        self.runner.run(core.restore_backup, self.win.node_dir, snap,
                        lambda t, l="info": bus.log.emit(t, l))
        self.win.reload_config()


# ---------------------------------------------------------------------------
# 验证中心页
# ---------------------------------------------------------------------------

class VerifyPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.last_results = []
        lay = QVBoxLayout(self)
        lay.addWidget(_label("验证中心", bold=True, size=20))
        lay.addWidget(_label("一键检查环境是否真正可用（模拟新终端环境，不产生副作用）。",
                             color=C["text_sub"]))
        btns = QHBoxLayout()
        btns.addWidget(_btn("一键验证", self.run_verify, kind="primary"))
        self.deep_cb = QCheckBox("含深度演练（真实安装测试包并卸载）")
        btns.addWidget(self.deep_cb)
        btns.addStretch(1)
        lay.addLayout(btns)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["检查项", "结果", "详情"])
        self.table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        row.addWidget(_btn("一键修复失败项", self.auto_fix, kind="primary"))
        row.addWidget(_btn("导出报告", self.export))
        self.summary = _label("", bold=True)
        row.addWidget(self.summary)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        self.runner = TaskRunner(on_done=self._on_results)

    def run_verify(self):
        if not self.win.node_dir:
            QMessageBox.information(self, "提示", "未指定 Node 目录，请先添加/检测环境")
            return
        self.table.setRowCount(0)
        self.summary.setText("验证中…")
        self.runner.run(core.verify_all, self.win.node_dir, self.deep_cb.isChecked(),
                        lambda t, l="info": bus.log.emit(t, l))

    def _on_results(self, results):
        self.last_results = results
        self.table.setRowCount(0)
        failed = 0
        for r in results:
            i = self.table.rowCount()
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(r["name"]))
            ok = r["ok"]
            if not ok:
                failed += 1
            item = QTableWidgetItem("通过" if ok else "失败")
            item.setForeground(QColor(C["ok"] if ok else C["error"]))
            self.table.setItem(i, 1, item)
            self.table.setItem(i, 2, QTableWidgetItem(r["detail"]))
        self.summary.setText("环境就绪 ✓" if failed == 0
                             else f"{failed} 项失败，可点击「一键修复失败项」")
        self.summary.setStyleSheet(f"color:{C['ok']};" if failed == 0
                                   else f"color:{C['error']};")

    def auto_fix(self):
        if not self.last_results:
            QMessageBox.information(self, "提示", "请先运行一键验证")
            return
        self.runner.run(core.auto_fix, self.win.node_dir, self.last_results,
                        lambda t, l="info": bus.log.emit(t, l))

    def export(self):
        if not self.last_results:
            QMessageBox.information(self, "提示", "请先运行一键验证")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出验证报告",
                                              f"node-env-verify-{time.strftime('%Y%m%d_%H%M%S')}.txt",
                                              "文本文件 (*.txt)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"node-env 验证报告  {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Node 目录：{self.win.node_dir}\n\n")
            for r in self.last_results:
                f.write(f"[{'PASS' if r['ok'] else 'FAIL'}] {r['name']} — {r['detail']}\n")
        bus.log.emit(f"[验证] 报告已导出：{path}", "ok")


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("node-envbox · Node.js 环境管理")
        self.resize(960, 680)

        self.cfg = cfg_mod.default_config()
        self.cfg_base = r"C:\nodejs"
        self.current_env = None
        self._bootstrap()

        # 日志面板：固定底部区域（标题栏 + 内容），折叠 = 压缩到标题栏高度
        self.log_panel = LogPanel()
        self.log_panel.setMinimumHeight(120)
        self.log_area = QWidget()
        self.log_area.setObjectName("logArea")
        log_lay = QVBoxLayout(self.log_area)
        log_lay.setContentsMargins(0, 0, 0, 0)
        log_lay.setSpacing(0)
        # 标题栏
        bar = QWidget()
        bar.setObjectName("dockBar")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(14, 5, 8, 5)
        bar_lay.setSpacing(8)
        bar_lay.addWidget(_label("运行日志", bold=True))
        bar_lay.addStretch(1)
        self.log_toggle_btn = QToolButton()
        self.log_toggle_btn.setObjectName("logToggle")
        self.log_toggle_btn.setArrowType(Qt.DownArrow)
        self.log_toggle_btn.setAutoRaise(True)
        self.log_toggle_btn.setToolTip("折叠日志面板")
        self.log_toggle_btn.clicked.connect(self._toggle_log)
        bar_lay.addWidget(self.log_toggle_btn)
        log_lay.addWidget(bar)
        log_lay.addWidget(self.log_panel)
        self._log_expand_h = None  # 记住展开时的高度，折叠恢复用
        bus.log.connect(self.log_panel.append_line)

        # 左侧导航 + 页面
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(150)
        for name in ["概览", "初始化配置", "镜像源", "全局包", "环境变量",
                     "备份回滚", "验证中心"]:
            QListWidgetItem(name, self.nav)
        self.nav.currentRowChanged.connect(self._switch_page)

        self.stack = QStackedWidget()
        self.pages = {
            "overview": OverviewPage(self),
            "setup": SetupPage(self),
            "mirrors": MirrorsPage(self),
            "packages": PackagesPage(self),
            "envvars": EnvVarsPage(self),
            "backup": BackupPage(self),
            "verify": VerifyPage(self),
        }
        for p in self.pages.values():
            self.stack.addWidget(p)

        central = QWidget()
        root_lay = QVBoxLayout(central)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)
        main_row = QHBoxLayout()
        main_row.setContentsMargins(0, 0, 0, 0)
        main_row.addWidget(self.nav)
        main_row.addWidget(self.stack, 1)
        root_lay.addLayout(main_row, 1)   # 内容区占满剩余空间
        root_lay.addWidget(self.log_area)  # 底部日志区（自然高度，折叠时压缩）
        self.setCentralWidget(central)

        self.nav.setCurrentRow(0)
        self.statusBar().showMessage("")
        self.update_statusbar()
        cur = self.current_env or {}
        bus.log.emit(f"[启动] 环境：{cur.get('name') or '未检测到'} · "
                     f"目录：{cur.get('dir') or '—'} · "
                     f"配置：{cfg_mod.config_path(self.cfg_base)}", "info")
        # 检查失效镜像源并提醒（不删除用户数据，用户可自行决定）
        for m in self.cfg.get("mirrors", []):
            hint = cfg_mod.DEPRECATED_MIRROR_URLS.get(m["url"].strip())
            if hint:
                bus.log.emit(f"[镜像源]「{m['name']}」已失效：{hint}"
                             f"（请到镜像源页删除或更换 URL）", "warn")

    def _bootstrap(self):
        # v2 多环境流程：确定主配置位置 -> 加载/迁移 -> 扫描系统环境 -> 选定当前环境
        base = core.get_node_dir() or r"C:\nodejs"
        self.cfg_base = os.path.normpath(base)
        self.cfg = cfg_mod.load_config(self.cfg_base)
        auto_dirs = core.detect_node_dirs()
        if not auto_dirs and os.path.isfile(os.path.join(base, "node.exe")):
            auto_dirs = [os.path.normpath(base)]
        envs.ensure_initialized(self.cfg, auto_dirs)
        self.current_env = envs.pick_active(self.cfg)
        cfg_mod.save_config(self.cfg_base, self.cfg)  # 持久化首次扫描结果

    @property
    def node_dir(self):
        """当前生效环境的 Node 目录（无环境时为 None）。所有页面经此取目录。"""
        return (self.current_env or {}).get("dir") or None

    def save_cfg(self):
        cfg_mod.save_config(self.cfg_base, self.cfg)

    def reload_config(self):
        self.cfg = cfg_mod.load_config(self.cfg_base)
        self.current_env = envs.pick_active(self.cfg)
        bus.log.emit("[配置] 配置已重新加载", "info")

    def update_statusbar(self):
        e = self.current_env or {}
        if not e.get("dir"):
            self.statusBar().showMessage("未指定 Node 环境")
            return
        ver = core.node_version(e["dir"])
        reg = core.npm_config_get(e["dir"], "registry")
        self.statusBar().showMessage(f"环境：{e['name']}  ·  {e['dir']}  ·  "
                                     f"{ver}  ·  registry：{reg}")

    def _switch_page(self, row):
        self.stack.setCurrentIndex(row)

    def _toggle_log(self):
        """折叠 / 展开日志面板。

        折叠：隐藏内容 + 将日志区高度压缩到标题栏（约 40px），不留残留区；
        展开：恢复此前记录的高度（无则用默认 180px）。
        """
        if self.log_panel.isVisible():
            self._log_expand_h = self.log_area.height()   # 记住当前展开高度
            self.log_panel.setVisible(False)
            bar_h = self.log_toggle_btn.height() + 22     # 按钮 + 上下 margin
            self.log_area.setFixedHeight(max(bar_h, 40))
            self.log_toggle_btn.setArrowType(Qt.UpArrow)
            self.log_toggle_btn.setToolTip("展开日志面板")
        else:
            self.log_panel.setVisible(True)
            h = self._log_expand_h or 180
            self.log_area.setFixedHeight(h)
            self.log_toggle_btn.setArrowType(Qt.DownArrow)
            self.log_toggle_btn.setToolTip("折叠日志面板")
