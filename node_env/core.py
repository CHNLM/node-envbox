"""核心逻辑层：与 Qt 完全解耦，可在任意线程调用。

包含：Node 目录检测、node/npm 命令执行、npm 配置读写、
环境变量读写（winreg，用户级 + 系统级）、配置备份与回滚、
操作历史记录、验证中心（全链路检查 + 深度演练）、镜像连通性检测、全局包管理。
"""

import ctypes
import json
import os
import shutil
import subprocess
import time
import urllib.request
import winreg


def _noop(msg: str, level: str = "info"):
    pass


# ---------------------------------------------------------------------------
# 基础命令执行
# ---------------------------------------------------------------------------

def run_cmd(args, timeout=120, env=None):
    """执行命令，返回 (returncode, stdout, stderr)。永不抛异常。

    GUI 进程（无控制台）启动子进程时，Windows 会为每个子进程新建一个
    黑色控制台窗口；用 CREATE_NO_WINDOW 彻底隐藏（npm/node 命令均经此）。"""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows: 0x08000000
    try:
        p = subprocess.run(args, capture_output=True, text=True,
                           timeout=timeout, env=env, creationflags=flags)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return -1, "", "执行超时"
    except Exception as e:
        return -1, "", str(e)


def _npm(node_dir):
    return os.path.join(node_dir, "npm.cmd")


def npm_run(node_dir, *args, timeout=120):
    return run_cmd(["cmd", "/c", _npm(node_dir), *args], timeout=timeout)


def node_run(node_dir, *args, timeout=60, env=None):
    return run_cmd([os.path.join(node_dir, "node.exe"), *args],
                   timeout=timeout, env=env)


# ---------------------------------------------------------------------------
# 目录检测
# ---------------------------------------------------------------------------

def which_in_path(exe, path):
    """在 PATH 字符串里找第一个命中的可执行文件（Windows 风格分号分隔）。"""
    if not path:
        return None
    for d in path.split(";"):
        d = d.strip().strip('"')
        if not d:
            continue
        cand = os.path.join(d, exe)
        if os.path.isfile(cand):
            return cand
    return None


def get_node_dir(override=""):
    """检测 Node 安装目录：显式指定 -> NODE_HOME -> PATH -> 常见路径。"""
    if override and os.path.isfile(os.path.join(override, "node.exe")):
        return os.path.normpath(override)
    home = os.environ.get("NODE_HOME", "")
    if home and os.path.isfile(os.path.join(home, "node.exe")):
        return os.path.normpath(home)
    found = which_in_path("node.exe", os.environ.get("PATH", ""))
    if found:
        return os.path.dirname(found)
    if os.path.isfile(r"C:\nodejs\node.exe"):
        return r"C:\nodejs"
    return None


# 常见 Node 安装路径（自动检测兜底）
COMMON_NODE_DIRS = [
    r"C:\nodejs",
    r"C:\Program Files\nodejs",
    r"C:\Program Files (x86)\nodejs",
]


def detect_node_dirs():
    """扫描所有可能含 node.exe 的目录并去重（模拟新终端 PATH + 常见路径 + NODE_HOME）。

    返回规范化目录列表。用于多环境模型的自动检测。
    """
    dirs = []
    for d in merged_path_entries() + COMMON_NODE_DIRS:
        if d and os.path.isfile(os.path.join(d, "node.exe")):
            norm = os.path.normpath(d)
            if norm not in dirs:
                dirs.append(norm)
    home = os.environ.get("NODE_HOME", "")
    if home and os.path.isfile(os.path.join(home, "node.exe")):
        norm = os.path.normpath(home)
        if norm not in dirs:
            dirs.append(norm)
    return dirs


def env_probe(node_dir):
    """探测单个 Node 环境的运行时信息（概览页卡片用）。失败字段返回占位符。"""
    return {
        "node": node_version(node_dir),
        "npm": npm_version(node_dir),
        "registry": npm_config_get(node_dir, "registry") or "—",
        "pkgs": str(len(list_global_packages(node_dir))),
    }


def node_version(node_dir):
    rc, out, err = node_run(node_dir, "-v")
    return out if rc == 0 else f"获取失败：{err}"


def npm_version(node_dir):
    rc, out, err = npm_run(node_dir, "-v")
    return out if rc == 0 else f"获取失败：{err}"


def npm_config_get(node_dir, key):
    rc, out, err = npm_run(node_dir, "config", "get", key)
    return out if rc == 0 else ""


def npm_config_set(node_dir, key, value, log=_noop):
    backup_before_mutate(node_dir, f"npm set {key}", log)
    rc, out, err = npm_run(node_dir, "config", "set", key, value)
    ok = rc == 0
    if ok:
        log(f"[npm] {key} = {value}", "ok")
    else:
        log(f"[npm] 设置 {key} 失败：{err}", "error")
    log_history(node_dir, f"npm config set {key}", value, ok)
    return ok


# ---------------------------------------------------------------------------
# 环境变量（winreg）
# ---------------------------------------------------------------------------

_ENV_KEY = {
    "user": (winreg.HKEY_CURRENT_USER, r"Environment"),
    "system": (winreg.HKEY_LOCAL_MACHINE,
               r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
}


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def broadcast_env_change():
    """广播 WM_SETTINGCHANGE，让新开进程立即读到新环境变量。"""
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    try:
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", 2, 5000, None)
    except Exception:
        pass


def get_env_var(scope, name):
    try:
        hkey, key_path = _ENV_KEY[scope]
        with winreg.OpenKey(hkey, key_path) as k:
            try:
                return winreg.QueryValueEx(k, name)[0]
            except FileNotFoundError:
                return None
    except OSError:
        return None


def set_env_var(scope, name, value, log=_noop):
    if scope == "system" and not is_admin():
        log("[环境变量] 写系统级需要管理员权限", "error")
        return False
    try:
        hkey, key_path = _ENV_KEY[scope]
        with winreg.OpenKey(hkey, key_path, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_EXPAND_SZ, str(value))
        broadcast_env_change()
        log(f"[环境变量] {scope} {name} = {value}", "ok")
        return True
    except Exception as e:
        log(f"[环境变量] 写入 {scope} {name} 失败：{e}", "error")
        return False


def split_path(path):
    if not path:
        return []
    out = []
    for e in path.split(";"):
        e = e.strip().strip('"')
        if e and e not in out:
            out.append(e)
    return out


def get_path_entries(scope):
    return split_path(get_env_var(scope, "Path"))


def merged_path_entries():
    """模拟新终端的完整 PATH：系统级在前，用户级追加在后。"""
    return get_path_entries("system") + get_path_entries("user")


def set_path_entries(scope, entries, log=_noop):
    return set_env_var(scope, "Path", ";".join(entries), log)


# ---------------------------------------------------------------------------
# 备份 / 回滚 / 历史
# ---------------------------------------------------------------------------

def backup_dir(node_dir):
    return os.path.join(node_dir, ".backup")


def history_path(node_dir):
    return os.path.join(backup_dir(node_dir), "history.jsonl")


def log_history(node_dir, action, detail="", ok=True):
    try:
        os.makedirs(backup_dir(node_dir), exist_ok=True)
        rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
               "action": action, "detail": detail, "ok": bool(ok)}
        with open(history_path(node_dir), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def list_history(node_dir, limit=300):
    if not os.path.exists(history_path(node_dir)):
        return []
    try:
        with open(history_path(node_dir), "r", encoding="utf-8") as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        return [json.loads(l) for l in lines[-limit:]]
    except Exception:
        return []


def create_backup(node_dir, reason="manual", log=_noop):
    """对 .npmrc、环境变量、node-env.json 打快照。返回快照目录。"""
    if not node_dir:
        return None
    snap = os.path.join(backup_dir(node_dir),
                        "snap_" + time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(snap, exist_ok=True)
    home_npmrc = os.path.join(os.path.expanduser("~"), ".npmrc")
    if os.path.exists(home_npmrc):
        shutil.copy2(home_npmrc, os.path.join(snap, "npmrc"))
    env = {
        "user_path": get_path_entries("user"),
        "system_path": get_path_entries("system"),
        "user_node_path": get_env_var("user", "NODE_PATH"),
        "system_node_path": get_env_var("system", "NODE_PATH"),
    }
    with open(os.path.join(snap, "env.json"), "w", encoding="utf-8") as f:
        json.dump(env, f, ensure_ascii=False, indent=2)
    cfg = os.path.join(node_dir, "node-env.json")
    if os.path.exists(cfg):
        shutil.copy2(cfg, os.path.join(snap, "config.json"))
    manifest = {"created": time.strftime("%Y-%m-%d %H:%M:%S"),
                "reason": reason, "node_dir": node_dir}
    with open(os.path.join(snap, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    log(f"[备份] 快照已创建：{snap}", "ok")
    return snap


def backup_before_mutate(node_dir, reason, log=_noop):
    if node_dir:
        create_backup(node_dir, reason, log)


def list_backups(node_dir):
    bd = backup_dir(node_dir)
    if not os.path.isdir(bd):
        return []
    snaps = [os.path.join(bd, d) for d in os.listdir(bd)
             if d.startswith("snap_") and os.path.isdir(os.path.join(bd, d))]
    return sorted(snaps, reverse=True)


def restore_backup(node_dir, snap, log=_noop):
    """从快照还原 .npmrc / 用户环境变量 / node-env.json。"""
    if not os.path.isdir(snap):
        log(f"[回滚] 快照不存在：{snap}", "error")
        return False
    try:
        npmrc = os.path.join(snap, "npmrc")
        if os.path.exists(npmrc):
            shutil.copy2(npmrc, os.path.join(os.path.expanduser("~"), ".npmrc"))
        env_file = os.path.join(snap, "env.json")
        if os.path.exists(env_file):
            with open(env_file, "r", encoding="utf-8") as f:
                env = json.load(f)
            if env.get("user_path") is not None:
                set_path_entries("user", env["user_path"])
            np = env.get("user_node_path")
            if np is not None:
                set_env_var("user", "NODE_PATH", np or "")
        cfg = os.path.join(snap, "config.json")
        if os.path.exists(cfg):
            shutil.copy2(cfg, os.path.join(node_dir, "node-env.json"))
        log(f"[回滚] 已从快照还原：{snap}", "ok")
        log_history(node_dir, "restore", snap, True)
        return True
    except Exception as e:
        log(f"[回滚] 失败：{e}", "error")
        return False


# ---------------------------------------------------------------------------
# 镜像源 / 连通性
# ---------------------------------------------------------------------------

def set_registry(node_dir, url, log=_noop):
    ok = npm_config_set(node_dir, "registry", url, log)
    if ok:
        log_history(node_dir, "set registry", url, True)
    return ok


def ping_url(url, timeout=5):
    """探测 npm registry 镜像连通性。返回 (ok, 描述)。

    探测的是「registry 包元数据路径」（url + /left-pad），而非根路径——
    根路径 404 是 registry 常态（如 npmjs 根路径也返回 JSON 是特例），
    只有包路径能真实反映「npm install 是否可用」。
    任何 HTTP 状态码（含 4xx/5xx）都说明服务器已响应；只有
    连接失败/超时/DNS 失败才算不可达。
    """
    base = url.rstrip("/")
    probe_url = base + "/left-pad"
    t0 = time.time()
    try:
        req = urllib.request.Request(probe_url, method="GET",
                                     headers={"User-Agent": "node-env/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ms = int((time.time() - t0) * 1000)
            return True, f"{ms}ms"
    except urllib.error.HTTPError as e:
        ms = int((time.time() - t0) * 1000)
        # 服务器已响应但包路径不可用（如镜像已下线返回 404）
        return False, f"HTTP {e.code} · {ms}ms"
    except Exception as e:
        return False, f"{e}"[:60]


# ---------------------------------------------------------------------------
# 全局包管理
# ---------------------------------------------------------------------------

def list_global_packages(node_dir):
    """返回 [(名称, 版本)]。"""
    rc, out, err = npm_run(node_dir, "ls", "-g", "--depth=0", "--json")
    if rc != 0:
        return []
    try:
        data = json.loads(out)
        deps = (data.get("dependencies") or {})
        return [(k, (v or {}).get("version", "")) for k, v in deps.items()]
    except Exception:
        return []


def uninstall_global(node_dir, pkg, log=_noop):
    rc, out, err = npm_run(node_dir, "uninstall", "-g", pkg)
    ok = rc == 0
    log(f"[包管理] 卸载 {pkg} {'成功' if ok else '失败：' + err}", "ok" if ok else "error")
    log_history(node_dir, "uninstall -g", pkg, ok)
    return ok


def cache_clean(node_dir, log=_noop):
    rc, out, err = npm_run(node_dir, "cache", "clean", "--force")
    ok = rc == 0
    log(f"[包管理] npm cache clean {'成功' if ok else '失败：' + err}", "ok" if ok else "error")
    log_history(node_dir, "npm cache clean", "", ok)
    return ok


def dir_size(path):
    total = 0
    try:
        for root, _, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    except OSError:
        pass
    return total


# ---------------------------------------------------------------------------
# 验证中心
# ---------------------------------------------------------------------------

def _check_dir_writable(path):
    return os.path.isdir(path) and os.access(path, os.W_OK)


def verify_all(node_dir, deep=False, log=_noop, timeout=5):
    """全链路验证，返回 [{name, ok, detail}]。"""
    results = []

    # 1 版本可用
    rc, out, err = node_run(node_dir, "-v")
    rc2, out2, err2 = npm_run(node_dir, "-v")
    ok = rc == 0 and rc2 == 0
    results.append({"name": "node / npm 版本可用",
                    "ok": ok,
                    "detail": f"node {out or err} · npm {out2 or err2}"})

    # 2 目录结构
    dirs = ["node_global", "node_cache", "node_modules"]
    bad = [d for d in dirs if not _check_dir_writable(os.path.join(node_dir, d))]
    results.append({"name": "全局目录结构",
                    "ok": not bad,
                    "detail": "缺失/不可写：" + "、".join(bad) if bad else "三个目录均存在且可写"})

    # 3 npm 配置
    prefix = npm_config_get(node_dir, "prefix")
    cache = npm_config_get(node_dir, "cache")
    exp_pre = os.path.join(node_dir, "node_global")
    exp_cac = os.path.join(node_dir, "node_cache")
    ok = prefix and prefix.lower() == exp_pre.lower() and cache.lower() == exp_cac.lower()
    results.append({"name": "npm prefix / cache 配置",
                    "ok": ok,
                    "detail": f"prefix={prefix or '空'} · cache={cache or '空'}（目标 {exp_pre} / {exp_cac}）"})

    # 4 全局包解析
    rc, out, err = npm_run(node_dir, "ls", "-g", "--depth=0")
    results.append({"name": "全局包列表可读",
                    "ok": rc == 0,
                    "detail": out.splitlines()[-1] if out else err})

    # 5 PATH 命中（模拟新终端环境）
    merged = merged_path_entries()
    node_hit = which_in_path("node.exe", ";".join(merged))
    npm_hit = which_in_path("npm.cmd", ";".join(merged))
    ok = node_hit is not None and npm_hit is not None
    results.append({"name": "PATH 命令命中（模拟新终端）",
                    "ok": ok,
                    "detail": f"node → {node_hit or '未找到'} · npm → {npm_hit or '未找到'}"})

    # 6 镜像源连通
    reg = npm_config_get(node_dir, "registry")
    if reg:
        ok, ms = ping_url(reg, timeout)
        results.append({"name": "当前镜像源连通",
                        "ok": ok,
                        "detail": f"{reg} · {ms}"})
    else:
        results.append({"name": "当前镜像源连通", "ok": False, "detail": "未获取到 registry"})

    # 7 深度演练（可选）
    if deep:
        results.append(deep_test(node_dir, log))

    return results


def deep_test(node_dir, log=_noop):
    """真实安装一个微型包 -> 校验落点 -> require 验证 -> 卸载。"""
    pkg = "left-pad@1.3.0"
    try:
        rc, out, err = npm_run(node_dir, "install", "-g", pkg, "--no-fund", "--no-audit", timeout=180)
        if rc != 0:
            return {"name": "深度演练（真实安装）", "ok": False, "detail": f"安装失败：{err}"}
        target = os.path.join(node_dir, "node_global", "node_modules", "left-pad")
        if not os.path.isdir(target):
            return {"name": "深度演练（真实安装）", "ok": False, "detail": "未落在 node_global\\node_modules"}
        env = dict(os.environ)
        env["NODE_PATH"] = os.path.join(node_dir, "node_global", "node_modules")
        rc, out, err = node_run(node_dir, "-e", "require('left-pad')", env=env)
        npm_run(node_dir, "uninstall", "-g", "left-pad")
        if rc != 0:
            return {"name": "深度演练（真实安装）", "ok": False, "detail": f"require 失败：{err}"}
        return {"name": "深度演练（真实安装 + require + 卸载）", "ok": True,
                "detail": "安装落点正确，NODE_PATH require 生效，测试包已卸载"}
    except Exception as e:
        return {"name": "深度演练（真实安装）", "ok": False, "detail": str(e)}


def auto_fix(node_dir, results, log=_noop):
    """根据验证结果批量修复（修复前自动快照）。"""
    backup_before_mutate(node_dir, "auto-fix", log)
    fixed = []
    for r in results:
        if r["ok"]:
            continue
        name = r["name"]
        if "版本可用" in name:
            log("[修复] node/npm 无法执行，请检查目录完整性（需手动处理）", "error")
        elif "目录结构" in name:
            for d in ["node_global", "node_cache", "node_modules"]:
                os.makedirs(os.path.join(node_dir, d), exist_ok=True)
            fixed.append("目录结构")
        elif "配置" in name:
            npm_config_set(node_dir, "prefix", os.path.join(node_dir, "node_global"), log)
            npm_config_set(node_dir, "cache", os.path.join(node_dir, "node_cache"), log)
            fixed.append("npm 配置")
        elif "镜像源连通" in name:
            log("[修复] 当前源不可达，请在镜像源页切换或修改 URL（需手动选择）", "warn")
        elif "PATH" in name:
            add_user_path_entries(node_dir, log)
            fixed.append("PATH")
    log(f"[修复] 完成，共处理 {len(fixed)} 类问题", "ok" if fixed else "warn")
    return fixed


# ---------------------------------------------------------------------------
# 环境变量（用户级 PATH 条目管理）
# ---------------------------------------------------------------------------

def add_user_path_entries(node_dir, log=_noop, prepend=False):
    """把 Node 目录与 node_global 追加到用户级 PATH，并设置 NODE_PATH。

    prepend=True 时插入到 PATH 最前（便携/项目环境优先于系统环境）。
    """
    backup_before_mutate(node_dir, "env user path", log)
    targets = [node_dir, os.path.join(node_dir, "node_global")]
    entries = get_path_entries("user")
    changed = False
    for t in targets:
        if t in entries:
            continue
        if prepend:
            entries.insert(0, t)
        else:
            entries.append(t)
        changed = True
    if changed:
        set_path_entries("user", entries, log)
        log("[环境变量] 用户级 PATH 已%s Node 目录" % ("前置" if prepend else "追加"), "ok")
    else:
        log("[环境变量] 用户级 PATH 已包含所需目录，跳过", "info")
    np = os.path.join(node_dir, "node_global", "node_modules")
    if get_env_var("user", "NODE_PATH") != np:
        set_env_var("user", "NODE_PATH", np, log)
    return changed
