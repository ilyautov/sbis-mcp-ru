"""Каталог и упаковка. Числа в README и server.json проверяются, а не
переписываются руками: разошлись значит тест красный."""
from __future__ import annotations

import json
import re
from base64 import b64encode
from collections import Counter
from pathlib import Path
from urllib.parse import quote

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


def test_registry_description_fits():
    """MCP Registry отвечает 422 на описание длиннее 100 символов. Проверено
    на собственной шкуре 11.09.2026: пять публикаций упали разом."""
    sj = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert len(sj["description"]) <= 100, len(sj["description"])


def test_versions_agree():
    py = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    sj = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    version = re.search(r'^version = "([^"]+)"', py, re.M).group(1)
    assert sj["version"] == version
    assert sj["packages"][0]["version"] == version
    assert (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").count(f"[{version}]") >= 1


def test_summaries_are_clean_text():
    """В каталоге Диадока все 114 описаний приехали со значком ссылки из
    документации: символ из приватной области Unicode, невидимый в браузере и
    заметный в терминале. Он же попадал в слова и портил поиск."""
    def unclean(text: str) -> bool:
        return (text != text.strip()
                or any(ord(ch) < 32 or 0xE000 <= ord(ch) <= 0xF8FF for ch in text))

    dirty = [r["operation_id"] for r in rows() if unclean(str(r.get("summary", "")))]
    assert not dirty, dirty[:5]


def test_entities_file_ships_with_the_catalog():
    """Карта сущностей это половина поиска и весь инструмент sbis_map. Пока
    файла не было, map молча отдавал пустоту во всех пяти серверах."""
    ents = yaml.safe_load((ROOT / "sbis_mcp" / "entities.yaml").read_text(encoding="utf-8"))
    keys = {e["key"] for e in ents["entities"]}
    sections = {r["section"] for r in rows()}
    assert keys == sections, sections ^ keys
    pkg_data = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "entities.yaml" in pkg_data  # иначе файл не попадёт в колесо


def test_live_questions_hit_the_right_method():
    """Не внутренности ранжирования, а обещание: человек спрашивает словами, и
    сверху стоит тот метод, который он имел в виду."""
    from schema_mcp_core.entities import EntityIndex
    from schema_mcp_core.registry import Catalog

    idx = EntityIndex.load(ROOT / "sbis_mcp" / "entities.yaml")
    catalog = Catalog.from_yaml(CATALOG, entities=idx)
    for question, expected in [('список документов', 'sbis_spisok_dokumentov'), ('войти в систему', 'sbis_spisok_akkauntov'), ('сотрудники организации', 'sbis_spisok_nashih_organizaciy')]:
        top = catalog.search(question, limit=1)
        assert top, question
        assert top[0].operation_id == expected, (question, top[0].operation_id)


def test_skill_frontmatter_is_valid():
    skill = next((ROOT / "skills").glob("*/SKILL.md"))
    head = skill.read_text(encoding="utf-8").split("---")[1]
    meta = yaml.safe_load(head)
    assert set(meta) == {"name", "description"}, meta.keys()
    assert len(meta["description"]) <= 1024
