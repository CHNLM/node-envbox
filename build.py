#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""node-envbox Nuitka 打包脚本（替代 build.bat）。

用 Nuitka 将 app.py 打包为独立可执行程序（standalone），输出到 dist/ 目录。
- 程序图标：node-env.ico（嵌入 exe + 作为数据文件随包分发，供窗口图标使用）
- 纯 Python 实现，不受 cmd/PowerShell 活动代码页(936)影响。
用法：python build.py [--onefile]   （或双击 build.bat 薄封装）
"""

import ctypes
import os
import shutil
import subprocess
import sys
import winreg

# 强制 stdout/stderr 以 UTF-8 输出：GitHub Actions / 非中文 Windows 默认用
# cp1252 等编码，无法编码中文 print 会抛 UnicodeEncodeError（errors 兜底不崩）。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))


def _venv_python():
    """定位虚拟环境 Python：优先 .venv（uv 约定），回退到 venv（setup.py 约定）。"""
    for name in (".venv", "venv"):
        p = os.path.join(ROOT, name, "Scripts", "python.exe")
        if os.path.exists(p):
            return p
    return os.path.join(ROOT, "venv", "Scripts", "python.exe")
ICON = os.path.join(ROOT, "node-env.ico")
DIST_DIR = os.path.join(ROOT, "dist")

OUTPUT_NAME = "node-env.exe"

# 版本信息
COMPANY = "node-envbox"
PRODUCT = "node-envbox"
DESCRIPTION = "Portable Node.js Environment Manager"
VERSION = "1.0.0"

# 基础 Nuitka 参数（保持 --opt=value 格式）
NUITKA_ARGS = [
    "--standalone",
    "--enable-plugin=pyside6",
    "--windows-console-mode=disable",
    "--assume-yes-for-downloads",
    "--output-dir=dist",
    "--output-filename=" + OUTPUT_NAME,
    "--company-name=" + COMPANY,
    "--product-name=" + PRODUCT,
    "--file-description=" + DESCRIPTION,
    "--file-version=" + VERSION,
    "--product-version=" + VERSION,
    "--windows-icon-from-ico=node-env.ico",  # 嵌入 exe 文件图标（资源管理器显示）
    "--include-data-files=node-env.ico=node-env.ico",  # 图标随包分发（运行时窗口图标用）
]


def run(cmd, **kwargs):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)  # 防止外部 sitecustomize 干扰（如 WorkBuddy 沙箱）
    env.pop("PYTHONSTARTUP", None)
    kwargs.setdefault("env", env)
    print(f"\n>>> {' '.join(cmd)}")
    sys.stdout.flush()
    return subprocess.call(cmd, **kwargs)


def pause():
    """交互式暂停；非交互环境（如 CI/后台）下自动跳过。"""
    try:
        input("按回车键退出...")
    except EOFError:
        pass


def _load_reg_env(hive, path):
    """读取注册表键下全部字符串环境变量。"""
    vals = {}
    try:
        with winreg.OpenKey(hive, path) as k:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(k, i)
                    if isinstance(value, str):
                        vals[name] = value
                    i += 1
                except OSError:
                    break
    except OSError:
        pass
    return vals


def _expand_env(value):
    """展开 REG_EXPAND_SZ 类型值中的 %VAR%。"""
    if not isinstance(value, str) or "%" not in value:
        return value
    buf = ctypes.create_unicode_buffer(32768)
    ctypes.windll.kernel32.ExpandEnvironmentStringsW(value, buf, 32768)
    return buf.value


def _ensure_msvc_env():
    """从注册表合并完整 MSVC 工具链环境（便携 MSVC 无 VS 安装记录）。

    便携 MSVC（C:\\MSVC）把 PATH/INCLUDE/LIB 等写在用户环境变量里，
    后台进程/打包任务不一定继承最新注册表值。这里模拟新终端：
    1. HKLM + HKCU 合并进本进程环境（PATH 系统级在前、用户级追加）
    2. 从 VCToolsInstallDir 推导 VCToolsVersion —— Nuitka 对便携 MSVC
       的版本检测依赖该变量（SconsUtils.getMsvcVersion fallback），
       缺省时误报 "MSVC too old"（Python 3.13 需 >= 14.3）
    """
    sys_env = _load_reg_env(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")
    user_env = _load_reg_env(winreg.HKEY_CURRENT_USER, r"Environment")

    os.environ["Path"] = _expand_env(
        sys_env.get("Path", "") + ";" + user_env.get("Path", ""))
    for k, v in {**sys_env, **user_env}.items():
        if k.lower() == "path":
            continue
        os.environ[k] = _expand_env(v)

    if not os.environ.get("VCToolsVersion"):
        tools_dir = os.environ.get("VCToolsInstallDir", "")
        if tools_dir:
            os.environ["VCToolsVersion"] = os.path.basename(
                os.path.normpath(tools_dir))
            print(f"[info] VCToolsVersion={os.environ['VCToolsVersion']}"
                  f"（由 VCToolsInstallDir 推导）")


def _find_windows_kits():
    """定位 Windows Kits 10 的 Include 目录。

    优先从 INCLUDE 环境变量反推（MSVC 装到任意自定义目录都能覆盖），
    其次回退到常见安装位置（C:\\MSVC / Program Files (x86)）。
    返回首个存在的 <Kits>\\10\\Include 目录，找不到返回 None。
    """
    marker = os.path.join("Windows Kits", "10", "Include")
    for part in os.environ.get("INCLUDE", "").split(";"):
        p = part.strip()
        idx = p.find(marker)
        if idx >= 0:
            base = p[:idx].rstrip("\\;") + "\\" + marker
            if os.path.isdir(base):
                return base
    for base in [r"C:\MSVC\Windows Kits\10\Include",
                 os.path.join(os.environ.get("ProgramFiles(x86)", ""),
                              "Windows Kits", "10", "Include")]:
        if os.path.isdir(base):
            return base
    return None


def _ensure_windows_sdk_version():
    """Nuitka 靠环境变量 WindowsSDKVersion 判定 SDK 是否可用（该变量由 VS 的
    vcvarsall.bat 设置）。便携 MSVC 的 install 脚本只持久化了 PATH/INCLUDE/LIB，
    漏了它 → 每次打包都告警。这里自动探测版本并注入，已存在则跳过。"""
    if os.environ.get("WindowsSDKVersion"):
        return
    base = _find_windows_kits()
    if base:
        versions = sorted(v for v in os.listdir(base) if v.startswith("10."))
        if versions:
            ver = versions[-1]
            os.environ["WindowsSDKVersion"] = ver + "\\"
            print(f"[info] 自动注入 WindowsSDKVersion={ver}（来自 {base}）")
            return
    print("[warn] 未探测到 Windows Kits 目录，SDK 版本未知（不影响编译，仅缺版本元数据）")


def _parse_vc_version(ver):
    """解析 '14.51.36231' -> (14, 51)；无法解析返回 None。"""
    try:
        parts = ver.split(".")
        nums = [int(x) for x in parts]
        return tuple(nums[:2]) if len(nums) >= 2 else tuple(nums)
    except (ValueError, IndexError):
        return None


def _detect_vs_install():
    """检测正规 VS 安装（Nuitka 可自行 vswhere 定位）。返回安装路径或 None。"""
    vswhere = os.path.join(
        os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"),
        "Microsoft Visual Studio", "Installer", "vswhere.exe")
    try:
        out = subprocess.run(
            [vswhere, "-latest", "-products", "*",
             "-property", "installationPath"],
            capture_output=True, text=True, timeout=10).stdout.strip()
        return out or None
    except Exception:
        return None


def _check_toolchain():
    """打包前校验 MSVC 工具链可用，不可用时给出明确的修复指引并阻断。

    场景区分：
    - 便携 MSVC（注册表持久化）：cl.exe 应在 PATH、INCLUDE/LIB 已注入
    - 正规 VS 安装：环境变量由 vcvarsall.bat 动态设置，未注入时
      Nuitka 能自行检测 VS —— 仅提示、不阻断
    - MSVC 版本下限：Python 3.13 + Nuitka 要求工具集 >= 14.30（VS2022）
    """
    problems = []
    cl_path = shutil.which("cl.exe")
    env_ok = bool(os.environ.get("INCLUDE") and os.environ.get("LIB"))
    vs_path = _detect_vs_install()

    if not cl_path and not vs_path:
        problems.append(
            "未找到 cl.exe，且未检测到 Visual Studio 安装。请先准备 MSVC 工具链：\n"
            "  1) 便携 MSVC：运行 C:\\MSVC\\setup_x64_install.bat 后重启终端\n"
            "  2) 正规 VS：在「x64 Native Tools Command Prompt for VS」中运行本脚本")
    elif not cl_path and vs_path:
        # 正规 VS 已装但未注入工具链变量：Nuitka 能自动定位，仅提示
        print(f"[info] 检测到 Visual Studio：{vs_path}")
        print("[info] 当前环境未注入 VS 工具链变量，将依赖 Nuitka 自动检测；"
              "建议在「x64 Native Tools Command Prompt for VS」中运行以加速")
    elif cl_path and not env_ok:
        problems.append(
            "找到 cl.exe 但 INCLUDE/LIB 未设置（工具链环境注入不完整），"
            "请重新执行 MSVC install 脚本或 vcvarsall.bat。")

    ver = os.environ.get("VCToolsVersion", "")
    parsed = _parse_vc_version(ver) if ver else None
    # 注意：MSVC 工具集版本 14.29 属于 VS2019（过旧），14.30+ 才是 VS2022
    # （Python 3.13 + Nuitka 要求的 ">= 14.3" 指 14.3x 系列）
    if parsed and len(parsed) >= 2 and parsed < (14, 30):
        problems.append(
            f"当前 MSVC 版本 {ver} 过旧：Python 3.13 + Nuitka 要求 >= 14.30"
            "（VS2022 系列）。请升级 MSVC 工具链，"
            "或改用 Python 3.12 重建 venv。")

    if problems:
        print("\n[错误] MSVC 工具链不可用：")
        for p in problems:
            print("  - " + p)
        print("\n处理办法：")
        print("  1) 便携 MSVC：运行 setup_x64_install.bat 后重启终端")
        print("  2) 正规 VS：开始菜单打开「x64 Native Tools Command Prompt for VS」，在其中运行 build.py")
        print("  3) 或先手动执行 vcvarsall.bat 注入工具链环境")
        return False

    print(f"[ok] MSVC 工具链就绪：cl.exe={cl_path or '（由 Nuitka 自动定位）'}"
          + (f"，VCToolsVersion={ver}" if ver else ""))
    return True


def main():
    onefile = "--onefile" in sys.argv

    print("=" * 60)
    print(" node-envbox 打包")
    print("=" * 60)

    _ensure_msvc_env()
    _ensure_windows_sdk_version()
    if not _check_toolchain():
        pause()
        return 1

    VENV_PY = _venv_python()
    if not os.path.exists(VENV_PY):
        print("[错误] 未找到虚拟环境（.venv 或 venv），请先运行 setup.py 或 uv 创建环境。")
        pause()
        return 1
    if not os.path.exists(ICON):
        print(f"[错误] 未找到图标文件：{ICON}")
        pause()
        return 1

    args = list(NUITKA_ARGS)
    if onefile:
        args.append("--onefile")
        print("\n已启用 --onefile（单文件模式，体积更大、启动稍慢，便于分发）")

    print("\n[1/1] Nuitka 打包中（首次约 10-30 分钟，请耐心等待）...")
    cmd = [VENV_PY, "-m", "nuitka"] + args + ["app.py"]
    code = run(cmd, cwd=ROOT)
    if code != 0:
        print("\n[错误] 打包失败，请查看上方日志。")
        pause()
        return 1

    if onefile:
        exe = os.path.join(DIST_DIR, OUTPUT_NAME)
    else:
        exe = os.path.join(DIST_DIR, "app.dist", OUTPUT_NAME)

    print("\n" + "=" * 60)
    if os.path.exists(exe):
        size_mb = os.path.getsize(exe) / 1024 / 1024
        print(f" 打包完成：{exe}（{size_mb:.1f} MB）")
        print(f" 双击 {exe} 即可运行")
        print(" 单文件版：python build.py --onefile")
    else:
        print(f" 打包完成，但未找到预期产物 {exe}，请检查上方日志。")
    print("=" * 60)
    pause()
    return 0


if __name__ == "__main__":
    sys.exit(main())
