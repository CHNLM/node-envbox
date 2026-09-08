"""config 模块补充测试：_validate 边界 + _merge_default_mirrors 迁移合并。

使用 pytest 临时目录，不触碰真实配置。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from node_env import config as cfg_mod  # noqa: E402


# ---------------------------------------------------------------------------
# _validate 边界
# ---------------------------------------------------------------------------

def test_validate_rejects_non_dict():
    assert cfg_mod._validate(None) is False
    assert cfg_mod._validate("x") is False
    assert cfg_mod._validate([]) is False


def test_validate_accepts_v1():
    # version==1 视为合法（load 时自动迁移），不校验其余字段
    assert cfg_mod._validate({"version": 1}) is True


def test_validate_rejects_unknown_version():
    assert cfg_mod._validate({"version": 99}) is False


def test_validate_requires_mirrors_list():
    cfg = cfg_mod.default_config()
    assert cfg_mod._validate(cfg) is True
    cfg["mirrors"] = "not a list"
    assert cfg_mod._validate(cfg) is False


def test_validate_rejects_mirror_missing_name_or_url():
    cfg = cfg_mod.default_config()
    cfg["mirrors"] = [{"name": "", "url": "https://a.com"}]  # name 为空
    assert cfg_mod._validate(cfg) is False
    cfg["mirrors"] = [{"name": "x", "url": ""}]  # url 为空
    assert cfg_mod._validate(cfg) is False


def test_validate_rejects_non_http_mirror_url():
    cfg = cfg_mod.default_config()
    cfg["mirrors"] = [{"name": "x", "url": "ftp://bad"}]
    assert cfg_mod._validate(cfg) is False
    cfg["mirrors"] = [{"name": "x", "url": "git://bad"}]
    assert cfg_mod._validate(cfg) is False


def test_validate_rejects_bad_environment_entry():
    cfg = cfg_mod.default_config()
    cfg["environments"] = [{"id": "", "dir": ""}]  # id 为空
    assert cfg_mod._validate(cfg) is False
    cfg["environments"] = [{"id": "e1", "dir": 123}]  # dir 非字符串
    assert cfg_mod._validate(cfg) is False
    cfg["environments"] = ["not a dict"]
    assert cfg_mod._validate(cfg) is False


def test_validate_accepts_env_with_empty_dir():
    # 无 node 环境时 env_none 的 dir 为空字符串，属合法状态
    cfg = cfg_mod.default_config()
    cfg["environments"] = [{"id": "env_none", "dir": ""}]
    assert cfg_mod._validate(cfg) is True


# ---------------------------------------------------------------------------
# _merge_default_mirrors（新源自动合并，幂等）
# ---------------------------------------------------------------------------

def test_merge_adds_missing_default_mirrors(tmp_path):
    # 已有旧源：新默认源中缺失的部分应被追加，旧源保留
    cfg = {
        "version": 2,
        "active_env": "",
        "environments": [],
        "mirrors": [{"name": "旧源", "url": "https://registry.npmjs.org"}],
        "settings": {},
    }
    logs = []
    cfg_mod._merge_default_mirrors(str(tmp_path), cfg, lambda t, l="info": logs.append((t, l)))

    urls = {m["url"] for m in cfg["mirrors"]}
    assert "https://registry.npmjs.org" in urls          # 旧源保留
    for m in cfg_mod.DEFAULT_MIRRORS:
        assert m["url"] in urls                          # 所有新默认源已合并
    # 结果已落盘
    reloaded = cfg_mod.load_config(str(tmp_path))
    reload_urls = {m["url"] for m in reloaded["mirrors"]}
    assert reload_urls == urls


def test_merge_is_idempotent(tmp_path):
    cfg = cfg_mod.default_config()
    code = cfg_mod.save_config(str(tmp_path), cfg)
    assert code is None
    before = [m["url"] for m in cfg["mirrors"]]

    cfg_mod._merge_default_mirrors(str(tmp_path), cfg, lambda *a, **k: None)
    assert [m["url"] for m in cfg["mirrors"]] == before  # 二次加载无新增

    cfg_mod._merge_default_mirrors(str(tmp_path), cfg, lambda *a, **k: None)
    assert [m["url"] for m in cfg["mirrors"]] == before


def test_merge_dedup_by_url_case_and_slash(tmp_path):
    # 相同 URL（忽略大小写/尾部斜杠）不应重复合并
    url = "https://registry.npmmirror.com"
    cfg = {
        "version": 2,
        "active_env": "",
        "environments": [],
        "mirrors": [{"name": "用户源", "url": url + "/"}],  # 与默认源同 URL
        "settings": {},
    }
    cfg_mod._merge_default_mirrors(str(tmp_path), cfg, lambda *a, **k: None)
    cnt = sum(1 for m in cfg["mirrors"]
              if m["url"].strip().rstrip("/").lower() == url)
    assert cnt == 1  # 只保留用户自己的那条（URL 相同不入库重复源）