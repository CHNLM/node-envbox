"""node-env 核心层单元测试（不触碰真实机器配置，全部使用临时目录）。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from node_env import config as cfg_mod  # noqa: E402
from node_env import core  # noqa: E402
from node_env import envs  # noqa: E402


def test_default_config():
    c = cfg_mod.default_config()
    assert c["version"] == 2
    assert c["environments"] == []
    assert c["active_env"] == ""
    assert len(c["mirrors"]) == 4
    for m in c["mirrors"]:
        assert m["url"].startswith("http")


def test_config_repair(tmp_path):
    """损坏的配置文件应被备份并重建默认。"""
    (tmp_path / "node-env.json").write_text("{corrupt json", encoding="utf-8")
    c = cfg_mod.load_config(str(tmp_path))
    assert c["version"] == 2
    assert (tmp_path / "node-env.json").exists()
    corrupts = [f for f in os.listdir(tmp_path)
                if f.startswith("node-env.json.corrupt")]
    assert corrupts, "损坏文件应被重命名备份"


def test_config_roundtrip(tmp_path):
    c = cfg_mod.load_config(str(tmp_path))
    c["mirrors"].append({"name": "测试源", "url": "https://example.com/"})
    cfg_mod.save_config(str(tmp_path), c)
    c2 = cfg_mod.load_config(str(tmp_path))
    assert any(m["name"] == "测试源" for m in c2["mirrors"])


def test_config_rejects_bad_url(tmp_path):
    (tmp_path / "node-env.json").write_text(
        '{"version":2,"active_env":"","environments":[],'
        '"mirrors":[{"name":"x","url":"ftp://bad"}],"settings":{}}',
        encoding="utf-8")
    c = cfg_mod.load_config(str(tmp_path))
    # 不合法 URL 触发自修复，重建为默认
    assert all(m["url"].startswith(("http://", "https://")) for m in c["mirrors"])


def test_migrate_v1_to_v2(tmp_path):
    """v1 单环境配置应自动迁移为 v2 多环境结构，数据保留。"""
    (tmp_path / "node-env.json").write_text(
        '{"version":1,"mirrors":[{"name":"老源","url":"https://old.example.com"}],'
        '"settings":{"ping_timeout":3}}',
        encoding="utf-8")
    c = cfg_mod.load_config(str(tmp_path))
    assert c["version"] == 2
    assert any(m["name"] == "老源" for m in c["mirrors"])
    assert c["settings"]["ping_timeout"] == 3
    assert c["environments"] == []
    # 迁移后配置已落盘为 v2
    again = cfg_mod.load_config(str(tmp_path))
    assert again["version"] == 2


def test_split_path():
    assert core.split_path("") == []
    assert core.split_path(None) == []
    assert core.split_path("a;b;;c") == ["a", "b", "c"]
    assert core.split_path("x; x ") == ["x"]  # 去重 + 去空格
    assert core.split_path('"d:\\node";d:\\node') == [r"d:\node"]


def test_which_in_path():
    assert core.which_in_path("node.exe", "") is None
    assert core.which_in_path("node.exe", "C:\\nothing") is None
    assert core.which_in_path("node.exe", None) is None


def test_dir_size(tmp_path):
    p = tmp_path / "sub"
    p.mkdir()
    (p / "a.txt").write_text("12345")
    assert core.dir_size(str(p)) == 5


# ---------------------------------------------------------------------------
# 多环境管理（envs.py）
# ---------------------------------------------------------------------------

def test_envs_merge_dedup():
    cfg = cfg_mod.default_config()
    added = envs.merge_auto(cfg, [r"C:\nodejs", r"C:\nodejs", r"D:\portable\node"])
    assert added == 2
    assert len(cfg["environments"]) == 2
    dirs = [e["dir"] for e in cfg["environments"]]
    assert r"C:\nodejs" in dirs
    assert all(e["kind"] == "system" and e["auto_detect"] for e in cfg["environments"])
    # id 稳定：同一目录重复 merge 不新增
    assert envs.merge_auto(cfg, [r"C:\nodejs"]) == 0


def test_envs_ensure_initialized_fallback():
    cfg = cfg_mod.default_config()
    cur = envs.ensure_initialized(cfg, [r"C:\nodejs"])
    assert cur["dir"] == r"C:\nodejs"
    assert cfg["active_env"] == cur["id"]
    # active_env 失效时回退到第一个
    cfg["active_env"] = "nonexistent"
    cur2 = envs.pick_active(cfg)
    assert cur2["id"] == cfg["environments"][0]["id"]


def test_envs_ensure_initialized_empty():
    cfg = cfg_mod.default_config()
    cur = envs.ensure_initialized(cfg, [])
    assert cur["id"] == "env_none"
    assert cur["dir"] == ""


def test_envs_pick_active_none_when_empty():
    # 空配置时 pick_active 应返回 None（而非抛异常）
    assert envs.pick_active({}) is None
    assert envs.pick_active({"environments": []}) is None
    # environments 缺失字段时
    assert envs.pick_active({"environments": None}) is None


def test_envs_add_portable(tmp_path):
    fake = tmp_path / "node"
    fake.mkdir()
    (fake / "node.exe").write_bytes(b"MZ")
    cfg = cfg_mod.default_config()
    env = envs.add_environment(cfg, str(fake))
    assert env is not None
    assert env["kind"] == "portable"
    assert env["auto_detect"] is False
    # 重复添加返回同一环境（幂等）
    env2 = envs.add_environment(cfg, str(fake))
    assert env2["id"] == env["id"]
    assert len(cfg["environments"]) == 1
    # 目录不存在返回 None
    assert envs.add_environment(cfg, str(tmp_path / "nope")) is None
    # 目录里没有 node.exe 返回 None
    empty = tmp_path / "empty"
    empty.mkdir()
    assert envs.add_environment(cfg, str(empty)) is None


def test_envs_remove_environment():
    cfg = cfg_mod.default_config()
    envs.merge_auto(cfg, [r"C:\nodejs", r"D:\portable\node"])
    first_id = cfg["environments"][0]["id"]
    second_id = cfg["environments"][1]["id"]
    cfg["active_env"] = second_id
    assert envs.remove_environment(cfg, second_id) is True
    assert cfg["active_env"] == first_id  # 移除当前环境后回退
    assert envs.remove_environment(cfg, "not-exists") is False
