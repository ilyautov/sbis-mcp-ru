"""Контракт одноклик-бандла: serve.py, mcpb/manifest.json и pyproject.toml.

serve.py это единственная точка входа, на которую смотрит Claude Desktop внутри
.mcpb. Здесь закреплены три факта, на которых бандл держится: ключ сервиса,
список зависимостей для загрузочного окружения и совпадение версий манифеста и
pyproject. Разъедется любой из них, и бандл сломается молча.
"""
import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_serve():
    spec = importlib.util.spec_from_file_location("serve", ROOT / "serve.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _manifest():
    return json.loads((ROOT / "mcpb" / "manifest.json").read_text(encoding="utf-8"))


def _pyproject_version():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE).group(1)


def test_serve_declares_service():
    assert _load_serve().SERVICES == {"sbis": "sbis_mcp.server"}


def test_serve_deps_match_pyproject():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "schema-mcp-core>=0.2.0,<1" in text
    assert _load_serve().DEPS == ["schema-mcp-core>=0.2.0,<1"]


def test_manifest_version_matches_pyproject():
    assert _manifest()["version"] == _pyproject_version()


def test_manifest_entry_point_matches_bundle_layout():
    m = _manifest()
    assert m["server"]["entry_point"] == "server/serve.py"
    assert m["server"]["mcp_config"]["args"] == [
        "${__dirname}/server/serve.py", "sbis"
    ]


def test_manifest_carries_privacy_policy():
    # Каталог коннекторов Claude отклоняет расширение без политики по https.
    policies = _manifest().get("privacy_policies") or []
    assert policies and all(u.startswith("https://") for u in policies)


def test_manifest_env_matches_server_env_map():
    from sbis_mcp.server import SBIS_CONFIG
    env = _manifest()["server"]["mcp_config"]["env"]
    assert set(env) == set(SBIS_CONFIG.env_map.values())
