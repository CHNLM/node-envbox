"""node-env.json 配置读写与自修复（v2 多环境模型）。

配置存放在 Node 安装目录下（默认 C:\\nodejs\\node-env.json），随目录便携迁移。
v2 起支持多环境：environments 为这台机器上所有 Node 环境的清单（系统环境
自动检测 + 便携/项目环境手动添加），active_env 标记当前生效环境；
镜像源列表、程序设置全局共享。

v1（单环境）配置在首次加载时自动迁移为 v2，无需手工处理。
"""

import json
import os
import time


CONFIG_VERSION = 2
CONFIG_FILENAME = "node-env.json"

# 已知失效的 npm registry 镜像（启动时给出提示，不自动删除用户数据）
DEPRECATED_MIRROR_URLS = {
    "https://mirrors.tuna.tsinghua.edu.cn/npm/": "清华 TUNA npm 镜像已下线，请删除或替换",
    "https://npm.taobao.org/": "淘宝 npm 旧域名已迁移至 npmmirror.com，请更新 URL",
}

DEFAULT_MIRRORS = [
    # 实测可用（2026-08-05）：清华 TUNA npm 镜像已失效（包路径 404），替换为腾讯云/华为云
    {"name": "阿里云源", "url": "https://registry.npmmirror.com"},
    {"name": "腾讯云源", "url": "https://mirrors.cloud.tencent.com/npm/"},
    {"name": "华为云源", "url": "https://mirrors.huaweicloud.com/repository/npm/"},
    {"name": "官方源", "url": "https://registry.npmjs.org"},
]

DEFAULT_SETTINGS = {
    "auto_ping": True,          # 启动/切换后自动检测镜像连通性
    "ping_timeout": 5,          # 连通性检测超时（秒）
    "backup_before_mutate": True,  # 修改配置前自动快照
    "node_dir_override": "",    # v1 遗留字段，v2 已由 active_env 取代（保留兼容）
}


def _noop(msg: str, level: str = "info"):
    pass


def default_config() -> dict:
    return {
        "version": CONFIG_VERSION,
        "active_env": "",
        "environments": [],     # [{id, name, dir, kind, auto_detect}]
        "mirrors": [dict(m) for m in DEFAULT_MIRRORS],
        "settings": dict(DEFAULT_SETTINGS),
    }


def config_path(node_dir: str) -> str:
    return os.path.join(node_dir, CONFIG_FILENAME)


def _env_valid(e) -> bool:
    return (isinstance(e, dict) and isinstance(e.get("id"), str) and e["id"]
            and isinstance(e.get("dir"), str))


def _norm_url(u: str) -> str:
    """归一化 URL 用于去重比较：去首尾空白与尾部斜杠、转小写。"""
    return (u or "").strip().rstrip("/").lower()


def _merge_default_mirrors(node_dir: str, cfg: dict, log) -> None:
    """把新版本默认镜像源合并进已有配置（防止旧配置文件缺新源）。

    规则：
    - 按归一化 URL 去重，仅追加缺失的源到列表末尾
    - 不删除、不覆盖用户已有数据（失效源保留，由启动时失效提示提醒）
    - 幂等：二次加载无新增时不做任何写入
    """
    existing = {_norm_url(m.get("url", "")) for m in cfg.get("mirrors", [])}
    added = []
    for m in DEFAULT_MIRRORS:
        if _norm_url(m.get("url", "")) not in existing:
            cfg["mirrors"].append(dict(m))
            added.append(m["name"])
    if added:
        save_config(node_dir, cfg, log)
        log(f"[配置] 已合并新默认镜像源：{'、'.join(added)}（原有镜像源保持不变）", "ok")


def _validate(cfg: dict) -> bool:
    if not isinstance(cfg, dict):
        return False
    ver = cfg.get("version")
    if ver == 1:
        # v1 结构合法，load 时自动迁移
        return True
    if ver != CONFIG_VERSION:
        return False
    mirrors = cfg.get("mirrors")
    if not isinstance(mirrors, list):
        return False
    for m in mirrors:
        if not isinstance(m, dict) or not m.get("name") or not m.get("url"):
            return False
        if not str(m["url"]).startswith(("http://", "https://")):
            return False
    envs = cfg.get("environments")
    if not isinstance(envs, list) or not all(_env_valid(e) for e in envs):
        return False
    return True


def migrate_v1_to_v2(v1: dict) -> dict:
    """v1 单环境配置 -> v2 多环境结构（environments 留空，由启动扫描填充）。"""
    return {
        "version": CONFIG_VERSION,
        "active_env": "",
        "environments": [],
        "mirrors": v1.get("mirrors") or [dict(m) for m in DEFAULT_MIRRORS],
        "settings": {**DEFAULT_SETTINGS, **(v1.get("settings") or {})},
    }


def load_config(node_dir: str, log=None) -> dict:
    """读取配置；缺失则创建默认；v1 自动迁移 v2；损坏则备份后重建（自修复）。"""
    log = log or _noop
    path = config_path(node_dir)
    default = default_config()
    if not os.path.exists(path):
        save_config(node_dir, default)
        log(f"[配置] 已创建默认配置 {path}", "ok")
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not _validate(cfg):
            raise ValueError("配置结构不合法")
        if cfg.get("version", 1) < CONFIG_VERSION:
            cfg = migrate_v1_to_v2(cfg)
            save_config(node_dir, cfg)
            log(f"[配置] 已迁移到 v{CONFIG_VERSION} 多环境结构", "ok")
        # 合并缺失的 settings 键，保证新版本配置兼容
        for k, v in DEFAULT_SETTINGS.items():
            cfg.setdefault("settings", {}).setdefault(k, v)
        # 合并新版本新增的默认镜像源（去重、不删用户数据、幂等）
        _merge_default_mirrors(node_dir, cfg, log)
        return cfg
    except Exception as e:
        corrupt = f"{path}.corrupt-{time.strftime('%Y%m%d_%H%M%S')}"
        try:
            os.replace(path, corrupt)
            log(f"[配置] 配置文件损坏（{e}），已备份为 {corrupt} 并重建默认", "warn")
        except OSError:
            log(f"[配置] 配置文件损坏且无法备份（{e}），重建默认", "warn")
        save_config(node_dir, default)
        return default


def save_config(node_dir: str, cfg: dict, log=None) -> None:
    """原子写入：先写临时文件再替换，避免写入中途崩溃损坏配置。"""
    path = config_path(node_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
