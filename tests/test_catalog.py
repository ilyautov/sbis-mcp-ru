"""Каталог и упаковка. Числа в README и server.json проверяются, а не
переписываются руками: разошлись значит тест красный."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "sbis_mcp" / "endpoints.yaml"
SVC = "sbis"

def rows() -> list[dict]:
    return yaml.safe_load(CATALOG.read_text(encoding="utf-8"))["endpoints"]


def test_catalog_loads_and_is_not_empty():
    assert len(rows()) == 45


def test_every_record_has_the_fields_the_server_reads():
    for r in rows():
        for field in ("operation_id", "section", "method", "path", "safety", "summary"):
            assert r.get(field), f"{r.get('operation_id')}: пустое поле {field}"


def test_operation_ids_are_unique_and_prefixed():
    ids = [r["operation_id"] for r in rows()]
    assert len(ids) == len(set(ids)), "дубли operation_id"
    assert all(i.startswith(SVC + "_") for i in ids)


def test_no_rest_write_verb_is_marked_read():
    """Предохранитель: PUT, PATCH и DELETE меняют состояние в любом API, и
    пометка read провела бы их мимо подтверждения.

    POST сюда НЕ входит намеренно: у VK и СБИС через POST идёт весь транспорт,
    включая чтение, так что глагол там ничего не означает."""
    bad = [r["operation_id"] for r in rows()
           if r["method"].upper() in {"PUT", "PATCH", "DELETE"} and r["safety"] == "read"]
    assert not bad, f"пишущие методы помечены read: {bad[:5]}"


def test_no_create_is_marked_read():
    """`get_or_create` читает И создаёт. Классификатор видит только `get` в
    начале имени и метит чтением; тогда агент заводит сущность без спроса.
    Найдено ровно так в hh и Диадоке 11.09.2026."""
    bad = [r["operation_id"] for r in rows()
           if r["safety"] == "read" and "or_create" in r["operation_id"].lower()]
    assert not bad, f"создающие методы помечены read: {bad}"


def test_summaries_are_human_readable():
    short = [r["operation_id"] for r in rows() if len(r.get("summary", "")) < 10]
    assert not short, f"слишком короткие описания: {short[:5]}"


def test_safety_split_matches_readme():
    c = Counter(r["safety"] for r in rows())
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"**{len(rows())}** | **{c['read']}** | **{c['write']}** | **{c['destructive']}**" in text


def test_versions_agree():
    py = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    sj = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    version = re.search(r'^version = "([^"]+)"', py, re.M).group(1)
    assert sj["version"] == version
    assert sj["packages"][0]["version"] == version
    assert (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").count(f"[{version}]") >= 1


def test_skill_frontmatter_is_valid():
    skill = next((ROOT / "skills").glob("*/SKILL.md"))
    head = skill.read_text(encoding="utf-8").split("---")[1]
    meta = yaml.safe_load(head)
    assert set(meta) == {"name", "description"}, meta.keys()
    assert len(meta["description"]) <= 1024
