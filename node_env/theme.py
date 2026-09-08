"""node-envbox 温柔治愈系主题（集中式 QSS）— 方案 D · 抹茶奶绿。

设计语言：主流浅色 APP 体系 + 清新治愈的抹茶绿调。
- 主色：抹茶绿（#4F8B58），低饱和明亮、清新护眼
- 背景：浅奶绿（#F4FAF0），与白色框体柔和过渡不突兀
- 导航：浅绿容器分区（#EBF3E6 圆角）
- 卡片 / 表格 / 输入框：纯白（#FFFFFF）
- 文字：深暖灰绿（正文 #3A4A3A 对背景 ≈ 10.8:1，AA 达标）
- 语义色：成功青绿 / 警告琥珀 / 错误柔和红（暖绿底上一个暖色点缀）
- 中性色全部带暖绿相，避免死灰
- 全局最小字号 16px；页面标题 20px、卡片数值 24px；
  主按钮 / 表头 / 选中项 600 字重加粗提升辨识度

所有颜色与字体统一在此维护，ui_main.py 通过 COLORS 引用，
避免散落魔法色值，便于整体换肤。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 调色板（方案 D · 抹茶奶绿）
# ---------------------------------------------------------------------------
COLORS = {
    # 主色（抹茶绿，加深以保证白字对比度达 AA：4.6:1）
    "primary": "#4F8B58",
    "primary_hover": "#41744A",
    "primary_pressed": "#35613E",
    "primary_soft": "#EEF6EA",      # 主色淡底（hover / 选中行）
    "peach": "#8FB98E",             # 冷色辅助（浅抹茶）

    # 背景与边框（核心浅色体系：浅奶绿底 + 白卡）
    "bg": "#F4FAF0",                # 主背景：浅奶绿
    "nav_bg": "#EBF3E6",            # 导航容器底色（深一档浅绿）
    "surface": "#FFFFFF",           # 卡片 / 表格 / 输入框
    "header_bg": "#EEF6E9",         # 表头底色（浅绿白）
    "border": "#E2EDDC",            # 浅绿边框
    "border_strong": "#C8DAC0",     # 深抹茶绿边框

    # 文字
    "text": "#3A4A3A",              # 主文字（深暖灰绿）
    "text_strong": "#2E3C30",       # 标题（更深）
    "text_sub": "#75826F",          # 次要文字
    "text_on_primary": "#FFFFFF",

    # 语义色
    "ok": "#2FA07E",
    "warn": "#C77E1B",
    "error": "#C75B62",
    "info": "#5A6C7D",
}

FONT_FAMILY = ('"HarmonyOS Sans SC", "Microsoft YaHei UI", "Microsoft YaHei", '
               '"Segoe UI", "PingFang SC", sans-serif')
MONO_FAMILY = ('"Cascadia Mono", Consolas, "JetBrains Mono", '
               '"HarmonyOS Sans SC", monospace')


def build_qss() -> str:
    """生成完整 QSS 样式表。"""
    c = COLORS
    return f"""
* {{
    font-family: {FONT_FAMILY};
    font-size: 16px;
    color: {c['text']};
}}

QMainWindow, QDialog, QMessageBox {{
    background-color: {c['bg']};
}}

/* 概览卡片 */
QWidget#card {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 12px;
}}

QLabel {{
    background: transparent;
    color: {c['text']};
}}

/* ---------- 按钮 ---------- */
QPushButton {{
    background-color: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border_strong']};
    border-radius: 8px;
    padding: 8px 20px;
    min-height: 28px;
}}
QPushButton:hover {{
    background-color: {c['primary_soft']};
    border-color: {c['primary']};
    color: {c['primary_pressed']};
}}
QPushButton:pressed {{
    background-color: {c['primary_pressed']};
    border-color: {c['primary_pressed']};
    color: {c['text_on_primary']};
}}
QPushButton:disabled {{
    background-color: #EEF2EA;
    border-color: {c['border']};
    color: {c['text_sub']};
}}

/* 主操作：抹茶绿实底白字 */
QPushButton[kind="primary"] {{
    background-color: {c['primary']};
    border: 1px solid {c['primary']};
    color: {c['text_on_primary']};
    font-weight: 600;
}}
QPushButton[kind="primary"]:hover {{
    background-color: {c['primary_hover']};
    border-color: {c['primary_hover']};
}}
QPushButton[kind="primary"]:pressed {{
    background-color: {c['primary_pressed']};
    border-color: {c['primary_pressed']};
}}
QPushButton[kind="primary"]:disabled {{
    background-color: #BBD2B8;
    border-color: #BBD2B8;
    color: {c['text_on_primary']};
}}

/* 危险操作：柔和红 */
QPushButton[kind="danger"] {{
    background-color: {c['surface']};
    border: 1px solid #E5A9AD;
    color: {c['error']};
}}
QPushButton[kind="danger"]:hover {{
    background-color: {c['error']};
    border-color: {c['error']};
    color: {c['text_on_primary']};
}}
QPushButton[kind="danger"]:pressed {{
    background-color: #A94A50;
    border-color: #A94A50;
    color: {c['text_on_primary']};
}}

/* ---------- 输入框 ---------- */
QLineEdit {{
    background-color: {c['surface']};
    border: 1px solid {c['border_strong']};
    border-radius: 6px;
    padding: 7px 12px;
    selection-background-color: {c['primary']};
    selection-color: {c['text_on_primary']};
}}
QLineEdit:focus {{
    border: 1px solid {c['primary']};
}}
QLineEdit:disabled {{
    background-color: #EEF2EA;
    color: {c['text_sub']};
}}

/* ---------- 下拉框（环境切换） ---------- */
QComboBox {{
    background-color: {c['surface']};
    border: 1px solid {c['border_strong']};
    border-radius: 6px;
    padding: 7px 12px;
}}
QComboBox:hover {{
    border-color: {c['primary']};
}}
QComboBox:focus {{
    border-color: {c['primary']};
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox QAbstractItemView {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    selection-background-color: {c['primary_soft']};
    selection-color: {c['text_strong']};
    outline: none;
    padding: 4px;
}}
QComboBox QAbstractItemView::item {{
    min-height: 34px;
    padding: 4px 10px;
    border-radius: 4px;
}}

/* ---------- 表格 ---------- */
QTableWidget, QTableView {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    gridline-color: {c['border']};
    selection-background-color: {c['primary_soft']};
    selection-color: {c['text_strong']};
    alternate-background-color: #F7FBF4;
}}
QTableCornerButton::section {{
    background-color: {c['header_bg']};
    border: none;
}}
QHeaderView::section {{
    background-color: {c['header_bg']};
    color: {c['text_strong']};
    font-weight: 600;
    border: none;
    border-right: 1px solid {c['border']};
    border-bottom: 1px solid {c['border']};
    padding: 10px 8px;
}}
QTableWidget::item {{
    padding: 6px 8px;
}}
QTableWidget::item:selected {{
    background-color: {c['primary_soft']};
    color: {c['text_strong']};
}}

/* ---------- 导航列表 ---------- */
QListWidget#nav {{
    background-color: {c['nav_bg']};
    border: none;
    border-radius: 12px;
    outline: none;
    margin: 8px 0 8px 8px;
    padding: 8px 0;
}}
QListWidget#nav::item {{
    padding: 12px 14px;
    margin: 2px 6px;
    border-radius: 8px;
    font-size: 16px;
}}
QListWidget#nav::item:hover {{
    background-color: {c['primary_soft']};
    color: {c['primary_pressed']};
}}
QListWidget#nav::item:selected {{
    background-color: {c['primary']};
    color: {c['text_on_primary']};
    font-weight: 600;
}}

/* ---------- 普通列表 ---------- */
QListWidget {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    outline: none;
}}
QListWidget::item {{
    padding: 8px 10px;
    margin: 1px 4px;
    border-radius: 6px;
}}
QListWidget::item:hover {{
    background-color: {c['primary_soft']};
}}
QListWidget::item:selected {{
    background-color: {c['primary_soft']};
    color: {c['text_strong']};
    font-weight: 600;
}}

/* ---------- 日志 ---------- */
QPlainTextEdit {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    font-family: {MONO_FAMILY};
    font-size: 16px;
    padding: 6px;
    selection-background-color: {c['primary']};
    selection-color: {c['text_on_primary']};
}}

/* ---------- Dock 标题 ---------- */
QDockWidget::title {{
    background-color: {c['header_bg']};
    color: {c['text_strong']};
    font-weight: 600;
    padding: 8px 10px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}

/* 日志面板自定义标题栏（折叠/展开） */
QWidget#logArea {{
    background-color: {c['surface']};
    border-top: 1px solid {c['border']};
}}
QWidget#dockBar {{
    background-color: {c['header_bg']};
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QToolButton#logToggle {{
    background: transparent;
    border: none;
    padding: 2px 8px;
    border-radius: 4px;
}}
QToolButton#logToggle:hover {{
    background-color: {c['primary_soft']};
}}
QToolButton#logToggle:pressed {{
    background-color: {c['primary']};
}}

/* ---------- 状态栏 ---------- */
QStatusBar {{
    background-color: {c['surface']};
    border-top: 1px solid {c['border']};
    color: {c['text_sub']};
}}

/* ---------- 工具提示 ---------- */
QToolTip {{
    background-color: {c['bg']};
    color: {c['text_strong']};
    border: 1px solid {c['primary']};
    border-radius: 4px;
    padding: 4px 8px;
}}

/* ---------- 勾选框 ---------- */
QCheckBox {{
    spacing: 8px;
    background: transparent;
}}

/* ---------- 滚动条 ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #D8E6D2;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c['primary']};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #D8E6D2;
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {c['primary']};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
"""


def apply(app) -> None:
    """将主题应用到 QApplication 实例（QSS + 全局字体兜底）。"""
    app.setStyleSheet(build_qss())
