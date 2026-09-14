#!/usr/bin/env python3
"""Запускалка sbis-mcp-ru, поднимающая себе окружение сама.

Клиент MCP указывают на ЭТОТ файл. На первом запуске скрипт тихо создаёт
виртуальное окружение рядом с собой, ставит зависимости, подсовывает их
текущему процессу и стартует сервер. Дальше запуск мгновенный.

    python3 serve.py sbis               # запустить сервер
    python3 serve.py sbis --selfcheck   # проверить установку и выйти

Нужна именно она, а не `uvx sbis-mcp-ru`: бандл .mcpb для Claude Desktop
распаковывается в каталог без установленного пакета, и точке входа неоткуда
взяться. Весь служебный вывод идёт в STDERR, STDOUT остаётся чистым под stdio.

Схема заимствована у ilyautov/moysklad-mcp-ru (MIT).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = Path(os.environ.get("SBIS_MCP_VENV", HERE / ".venv"))
DEPS = ["schema-mcp-core>=0.3.0,<1"]
SERVICES = {"sbis": "sbis_mcp.server"}


def _log(msg: str) -> None:
    print(f"[sbis-mcp-ru] {msg}", file=sys.stderr, flush=True)


def _venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _venv_site_packages() -> list[Path]:
    if os.name == "nt":
        return [VENV / "Lib" / "site-packages"]
    return list(VENV.glob("lib/python*/site-packages"))


def _deps_importable() -> bool:
    try:
        import mcp  # noqa: F401
        import schema_mcp_core  # noqa: F401
        return True
    except ImportError:
        return False


def _inject_venv() -> bool:
    """Подцепить уже готовое окружение. Без этого каждый запуск дёргал бы pip
    вхолостую: родительский процесс пакетов не видит, даже когда они стоят."""
    added = False
    for sp in _venv_site_packages():
        if sp.is_dir() and str(sp) not in sys.path:
            sys.path.insert(0, str(sp))
            added = True
    return added and _deps_importable()


def _ensure_deps() -> bool:
    if _deps_importable() or _inject_venv():
        return True
    vpy = _venv_python()
    if not vpy.exists():
        _log(f"первый запуск, создаю окружение в {VENV} …")
        import venv
        try:
            venv.EnvBuilder(with_pip=True).create(VENV)
        except Exception as exc:  # ensurepip выломан: Debian без python3-venv
            _log(f"не удалось создать окружение: {exc}")
            _log("похоже, в этой сборке Python нет ensurepip. "
                 "Поставьте python3-venv (apt install python3-venv) "
                 f"или сервер напрямую: pip install {' '.join(DEPS)}")
            return False
    _log("ставлю зависимости (один раз) …")
    try:
        subprocess.run(
            [str(vpy), "-m", "pip", "install", "--quiet", "--upgrade", "pip", *DEPS],
            check=True, stdout=sys.stderr.fileno(), stderr=sys.stderr.fileno(),
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        _log(f"установка зависимостей не удалась: {exc}")
        return False
    for sp in _venv_site_packages():
        if sp.is_dir():
            sys.path.insert(0, str(sp))
    return _deps_importable()


def main() -> None:
    if sys.version_info < (3, 10):
        _log(f"нужен Python 3.10 или новее, найден {sys.version.split()[0]}.")
        sys.exit(1)
    args = list(sys.argv[1:])
    selfcheck = "--selfcheck" in args
    positional = [a for a in args if not a.startswith("-")]
    if not positional or positional[0] not in SERVICES:
        _log(f"использование: python serve.py [{'|'.join(SERVICES)}] [--selfcheck]")
        sys.exit(2)
    service = positional[0]

    sys.path.insert(0, str(HERE))  # чтобы импортировался sbis_mcp/ из бандла

    if not _ensure_deps():
        _log(f"зависимости недоступны. Поставьте вручную: pip install {' '.join(DEPS)}")
        sys.exit(1)

    import importlib
    server = importlib.import_module(SERVICES[service])

    if selfcheck:
        import asyncio
        tools = asyncio.run(server.mcp.list_tools())
        _log(f"selfcheck пройден: сервер {service} отдаёт {len(tools)} инструментов.")
        print(f"OK: {service} готов, инструментов {len(tools)}.")
        return

    server.main()


if __name__ == "__main__":
    main()
