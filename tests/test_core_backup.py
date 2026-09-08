"""core 模块备份/回滚/历史 补充测试。

关键点：备份/回滚涉及写真实用户 .npmrc 与注册表环境变量，
测试通过 monkeypatch 隔离这些副作用，全部数据落在 pytest 临时目录。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from node_env import core  # noqa: E402


# ---------------------------------------------------------------------------
# create_backup / list_backups
# ---------------------------------------------------------------------------

def test_create_backup_creates_snapshot(tmp_path):
    node_dir = str(tmp_path / "node")
    os.makedirs(node_dir)

    # 准备一个真实 home .npmrc 与 node-env.json，确保被打包进快照
    home_path = str(tmp_path / "home")
    os.environ["USERPROFILE"] = home_path
    os.makedirs(home_path, exist_ok=True)
    npmrc = os.path.join(home_path, ".npmrc")
    with open(npmrc, "w", encoding="utf-8") as f:
        f.write("registry=https://x\n")

    cfg_file = os.path.join(node_dir, "node-env.json")
    with open(cfg_file, "w", encoding="utf-8") as f:
        json.dump({"version": 2}, f)

    snap = core.create_backup(node_dir, reason="test")
    assert snap and os.path.isdir(snap)
    assert os.path.isfile(os.path.join(snap, "npmrc"))
    assert os.path.isfile(os.path.join(snap, "config.json"))
    assert os.path.isfile(os.path.join(snap, "env.json"))
    with open(os.path.join(snap, "manifest.json"), encoding="utf-8") as f:
        mani = json.load(f)
    assert mani["reason"] == "test"
    assert mani["node_dir"] == node_dir


def test_create_backup_none_when_no_dir(tmp_path):
    # node_dir 为空时应安全返回 None，不创建任何东西
    assert core.create_backup("") is None


def test_list_backups_newest_first(tmp_path, monkeypatch):
    node_dir = str(tmp_path / "node")
    os.makedirs(node_dir)
    core.log_history(node_dir, "a", "1", True)  # 先触发 backup_dir 创建
    # 快照目录名带秒级时间戳，多次创建需强制时间不同，否则会复用同一目录。
    # log_history(1) + 两次 create_backup(各2: 目录名+manifest) = 5 次调用
    times = iter(["20260101_000000", "20260101_000000",
                  "20260101_000001", "20260101_000001",
                  "20260101_000002"])
    monkeypatch.setattr(core.time, "strftime", lambda fmt: next(times))
    a = core.create_backup(node_dir, "a")
    b = core.create_backup(node_dir, "b")
    snaps = core.list_backups(node_dir)
    assert len(snaps) == 2
    assert a in snaps and b in snaps
    # 倒序：最新在前
    assert os.path.basename(snaps[0]) > os.path.basename(snaps[1])
    assert core.list_backups(str(tmp_path / "nonexistent")) == []


# ---------------------------------------------------------------------------
# log_history / list_history
# ---------------------------------------------------------------------------

def test_history_roundtrip(tmp_path):
    node_dir = str(tmp_path / "node")
    os.makedirs(node_dir)
    core.log_history(node_dir, "set registry", "https://x", True)
    core.log_history(node_dir, "uninstall -g", "pkg", False)
    recs = core.list_history(node_dir)
    assert len(recs) == 2
    assert recs[0]["action"] == "set registry" and recs[0]["ok"] is True
    assert recs[1]["action"] == "uninstall -g" and recs[1]["ok"] is False
    assert recs[1]["detail"] == "pkg"


def test_history_limit(tmp_path):
    node_dir = str(tmp_path / "node")
    os.makedirs(node_dir)
    for i in range(20):
        core.log_history(node_dir, "act", str(i), True)
    recs = core.list_history(node_dir, limit=5)
    assert len(recs) == 5
    assert recs[-1]["detail"] == "19"  # 保留最新


def test_history_missing_file(tmp_path):
    assert core.list_history(str(tmp_path / "node"), 10) == []


# ---------------------------------------------------------------------------
# restore_backup
# ---------------------------------------------------------------------------

def test_restore_restores_npmrc_and_config(tmp_path, monkeypatch):
    node_dir = str(tmp_path / "node")
    os.makedirs(node_dir)

    home_path = str(tmp_path / "home")
    os.environ["USERPROFILE"] = home_path
    os.makedirs(home_path, exist_ok=True)
    npmrc = os.path.join(home_path, ".npmrc")
    with open(npmrc, "w", encoding="utf-8") as f:
        f.write("OLD")
    cfg_file = os.path.join(node_dir, "node-env.json")
    with open(cfg_file, "w", encoding="utf-8") as f:
        json.dump({"version": 2, "old": True}, f)

    snap = core.create_backup(node_dir, reason="snap")
    # 改动：快照里替换为新值
    with open(os.path.join(snap, "npmrc"), "w", encoding="utf-8") as f:
        f.write("NEW")
    with open(os.path.join(snap, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"version": 2, "new": True}, f)

    # env.json 里不含 user_path/user_node_path 时，跳过注册表写入
    with open(os.path.join(snap, "env.json"), "w", encoding="utf-8") as f:
        json.dump({"user_path": None, "user_node_path": None}, f)

    assert core.restore_backup(node_dir, snap) is True
    with open(os.path.join(home_path, ".npmrc"), encoding="utf-8") as f:
        assert f.read() == "NEW"
    with open(os.path.join(node_dir, "node-env.json"), encoding="utf-8") as f:
        assert json.load(f)["new"] is True


def test_restore_missing_snapshot(tmp_path, monkeypatch):
    logs = []
    assert core.restore_backup(str(tmp_path / "node"),
                               str(tmp_path / "nope"),
                               lambda t, l="info": logs.append(t)) is False


def test_restore_sets_user_env(tmp_path, monkeypatch):
    """env.json 提供 user_path/user_node_path 时应写回用户环境变量。"""
    node_dir = str(tmp_path / "node")
    snap = os.path.join(node_dir, "snap_x")
    os.makedirs(snap, exist_ok=True)
    env_file = os.path.join(snap, "env.json")
    with open(env_file, "w", encoding="utf-8") as f:
        json.dump({"user_path": [r"D:\node", r"D:\node\node_global"],
                   "user_node_path": r"D:\node\node_global\node_modules"}, f)

    written = {}
    monkeypatch.setattr(core, "set_path_entries",
                        lambda scope, entries: written.update({"path": entries}))
    monkeypatch.setattr(core, "set_env_var",
                        lambda scope, name, value: written.update({"np": value}))
    assert core.restore_backup(node_dir, snap) is True
    assert written["path"] == [r"D:\node", r"D:\node\node_global"]
    assert written["np"] == r"D:\node\node_global\node_modules"