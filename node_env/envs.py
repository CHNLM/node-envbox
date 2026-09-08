"""多环境管理器（纯逻辑，无 Qt 依赖，可单元测试）。

环境模型（node-env.json v2 的 environments 条目）：
    {
        "id": str,           # 稳定标识（由目录哈希派生，重启不变）
        "name": str,         # 显示名
        "dir": str,          # node 目录（node.exe 所在目录）
        "kind": str,         # system（自动检测，系统 PATH/常见路径）
                             # portable（便携解压版，手工添加）
                             # project（项目内嵌版，手工添加）
        "auto_detect": bool  # 是否来自自动检测
    }

职责：
- merge_auto：把自动检测目录合并进配置（按 dir 去重）
- ensure_initialized：保证 environments 非空 + active_env 有效
- pick_active：返回当前生效环境
- add_environment / remove_environment：手工维护便携/项目环境
"""

from __future__ import annotations

import hashlib
import os

KIND_SYSTEM = "system"
KIND_PORTABLE = "portable"
KIND_PROJECT = "project"

KIND_LABEL = {
    KIND_SYSTEM: "系统环境",
    KIND_PORTABLE: "便携环境",
    KIND_PROJECT: "项目环境",
}


def _new_id(dirs: str) -> str:
    """由目录派生稳定 id（同一目录永远同一 id，active_env 持久化不漂移）。"""
    digest = hashlib.sha1(dirs.lower().encode("utf-8", "replace")).hexdigest()[:10]
    return f"env_{digest}"


def _env_name(d: str, kind: str) -> str:
    base = os.path.basename(os.path.normpath(d)) or d
    return f"{KIND_LABEL.get(kind, kind)} · {base}"


def merge_auto(cfg: dict, auto_dirs: list) -> int:
    """把自动检测到的目录合并进 environments（按 dir 去重）。返回新增数。"""
    envs = cfg.setdefault("environments", [])
    known = {os.path.normpath(e["dir"]).lower(): e for e in envs}
    added = 0
    for d in auto_dirs:
        if not d:
            continue
        key = os.path.normpath(d).lower()
        if key in known:
            continue
        env = {
            "id": _new_id(key),
            "name": _env_name(d, KIND_SYSTEM),
            "dir": os.path.normpath(d),
            "kind": KIND_SYSTEM,
            "auto_detect": True,
        }
        envs.append(env)
        known[key] = env
        added += 1
    return added


def ensure_initialized(cfg: dict, auto_dirs: list) -> dict:
    """合并自动检测结果，确保 environments 非空、active_env 有效。返回当前环境。"""
    merge_auto(cfg, auto_dirs or [])
    envs = cfg.setdefault("environments", [])
    if not envs:
        envs.append({
            "id": "env_none",
            "name": "未检测到 Node 环境",
            "dir": "",
            "kind": KIND_PORTABLE,
            "auto_detect": False,
        })
    active = cfg.get("active_env", "")
    if not any(e["id"] == active for e in envs):
        cfg["active_env"] = envs[0]["id"]
    return pick_active(cfg)


def pick_active(cfg: dict) -> dict | None:
    """返回 active_env 对应的环境；配置为空（或无 environments）时返回 None。"""
    envs = cfg.get("environments") or []
    for e in envs:
        if e["id"] == cfg.get("active_env", ""):
            return e
    return envs[0] if envs else None


def add_environment(cfg: dict, node_dir: str, name: str = "",
                    kind: str = KIND_PORTABLE) -> dict | None:
    """手工添加便携/项目环境。目录无效或已存在时返回 None / 既有环境。"""
    node_dir = os.path.normpath(node_dir)
    if not os.path.isfile(os.path.join(node_dir, "node.exe")):
        return None
    key = node_dir.lower()
    for e in cfg.get("environments", []):
        if os.path.normpath(e["dir"]).lower() == key:
            return e  # 已存在，幂等返回
    env = {
        "id": _new_id(key),
        "name": name or _env_name(node_dir, kind),
        "dir": node_dir,
        "kind": kind,
        "auto_detect": False,
    }
    cfg.setdefault("environments", []).append(env)
    return env


def remove_environment(cfg: dict, env_id: str) -> bool:
    """移除环境；若移除的是当前环境，自动回退到第一个。"""
    envs = cfg.get("environments", [])
    before = len(envs)
    cfg["environments"] = [e for e in envs if e["id"] != env_id]
    if len(cfg["environments"]) == before:
        return False
    if cfg.get("active_env") == env_id:
        cfg["active_env"] = (cfg["environments"][0]["id"]
                             if cfg["environments"] else "")
    return True
