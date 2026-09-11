#!/usr/bin/env python3
"""Собрать каталог команд Saby (СБИС) из scripts/sbis_commands.tsv.

У Saby нет ни OpenAPI, ни машиночитаемого справочника: команды описаны только
в HTML-справке. Поэтому список ведётся руками в TSV рядом, а этот скрипт
превращает его в каталог. Транспорт у Saby один на все команды: JSON-RPC 2.0
POST на /service/, имя команды лежит в теле запроса, не в пути.

    python3 scripts/ingest_sbis.py --catalog sbis_mcp/endpoints.yaml --apply
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

import yaml

SRC = Path(__file__).with_name("sbis_commands.tsv")
DOC = {
    "documents": "https://saby.ru/help/integration/api/documents",
    "auth": "https://saby.ru/help/integration/api/authentication",
    "users": "https://saby.ru/help/integration/api/user_reg",
    "signature": "https://saby.ru/help/integration/api/signature",
    "counteragents": "https://saby.ru/help/integration/api/counterparty",
    "organizations": "https://saby.ru/help/integration/api/partner",
    "poa": "https://saby.ru/help/integration/api/powers",
    "service": "https://saby.ru/help/integration/api/service_func",
}

# Транслитерация имён: латинский operation_id нужен, потому что имя команды
# попадает в имя инструмента MCP, а там кириллица не везде переживает дорогу.
TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
})

# Необратимое: «Уничтожить» у Saby означает удаление без восстановления,
# «Удалить» помечает документ удалённым (корзина), но данные ещё вернуть можно.
# Оба остаются destructive: агент обязан спросить. «Восстановить» — это запись.
DESTRUCTIVE = re.compile(r"^(Удалить|Уничтожить|SendRevocation)")
READ = re.compile(r"^(Список|Прочитать|Информация|Проверить|Get|Сформировать)")


def oid(cmd: str) -> str:
    name = cmd.split(".", 1)[1] if "." in cmd else cmd
    s = re.sub(r"(?<!^)(?=[A-ZА-Я])", "_", name)
    s = s.lower().translate(TRANSLIT)
    return "sbis_" + re.sub(r"[^a-z0-9_]+", "_", s).strip("_")


def safety(cmd: str) -> str:
    name = cmd.split(".", 1)[1] if "." in cmd else cmd
    if DESTRUCTIVE.match(name):
        return "destructive"
    return "read" if READ.match(name) else "write"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    path = Path(a.catalog)
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    rows: list[dict] = doc.get("endpoints", []) or []
    seen = {r["operation_id"] for r in rows}

    added = 0
    stats: Counter[str] = Counter()
    for line in SRC.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        section, cmd, summary = line.split("\t")
        o = oid(cmd)
        if o in seen:
            continue
        rows.append({
            "operation_id": o,
            "section": section,
            "method": "POST",
            "host": "online.sbis.ru",
            "path": "/service/",
            "scope": section,
            "safety": safety(cmd),
            "summary": summary,
            "doc": DOC.get(section, "https://saby.ru/help/integration/api"),
            "pagination": "offset" if section == "documents" else "none",
            # Имя команды едет в теле JSON-RPC, а не в пути: без него вызов
            # не адресуется, поэтому держим его отдельным полем каталога.
            "params": {"body": '{"jsonrpc":"2.0","method":"%s","params":{},"id":0}' % cmd},
        })
        seen.add(o)
        added += 1
        stats[safety(cmd)] += 1

    doc["default_host"] = "online.sbis.ru"
    doc["endpoints"] = rows
    print(f"new: {added} | catalog: {len(rows)}")
    print("safety:", dict(stats))
    if a.apply:
        path.write_text(
            yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100),
            encoding="utf-8",
        )
        print("WRITTEN", path)


if __name__ == "__main__":
    main()
