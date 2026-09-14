#!/usr/bin/env python3
"""Собрать бандл для Claude Desktop: dist/sbis-mcp-ru-v<ВЕРСИЯ>.mcpb

.mcpb это zip, который пользователь без терминала ставит двойным щелчком.
Манифест лежит в корне архива, рантайм под server/. Claude Desktop читает
user_config из манифеста, спрашивает ключи и передаёт их сервера через
переменные окружения.

    python3 scripts/package_mcpb.py           # собрать
    python3 scripts/package_mcpb.py --list    # собрать и показать содержимое

Бандл не тащит site-packages: serve.py ставит зависимости при первом запуске,
поэтому архив остаётся в десятки килобайт.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_SRC = ROOT / "mcpb" / "manifest.json"

# Что кладём: только то, что нужно на импорте и в рантайме.
INCLUDE_DIRS = ["sbis_mcp"]
INCLUDE_FILES = ["serve.py", "LICENSE"]

# Запрет второго уровня: применяется к каждому файлу даже внутри разрешённого
# каталога. Забытый секрет так не уедет.
EXCLUDE_PATTERNS = [
    "*/__pycache__/*", "__pycache__/*", "*.pyc", "*.pyo",
    "*/.pytest_cache/*", ".pytest_cache/*",
    "*.env", ".env", "*/.env", "*.env.*",
    "cabinets.json", "*/cabinets.json",
    "*.key", "*.pem", "*.secret", "*credentials.json",
    ".DS_Store", "*/.DS_Store",
]
SECRET_BASENAMES = {"cabinets.json", ".env"}


def read_field(field: str) -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(rf'^{field}\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not m:
        sys.exit(f"в pyproject.toml нет поля {field}")
    return m.group(1)


def is_excluded(rel: str) -> bool:
    posix = Path(rel).as_posix()
    for pat in EXCLUDE_PATTERNS:
        if fnmatch.fnmatch(posix, pat) or fnmatch.fnmatch("/" + posix, "*/" + pat):
            return True
    return bool(set(Path(posix).parts) & {".git", ".venv", "__pycache__",
                                          ".pytest_cache", "dist", "build"})


def zip_mode(p: Path) -> int:
    """Права внутри архива не зависят от машины сборки: 0o755 только точке
    входа с шебангом в корне, всему остальному 0o644."""
    if p.suffix == ".py" and p.parent == ROOT:
        try:
            with p.open("rb") as fh:
                if fh.read(2) == b"#!":
                    return 0o755
        except OSError:
            pass
    return 0o644


def collect_runtime() -> list[Path]:
    out: list[Path] = []
    for d in INCLUDE_DIRS:
        base = ROOT / d
        if not base.exists():
            sys.exit(f"нет обязательного каталога: {d}")
        for p in sorted(base.rglob("*")):
            if p.is_file() and not is_excluded(p.relative_to(ROOT).as_posix()):
                out.append(p)
    for f in INCLUDE_FILES:
        p = ROOT / f
        if not p.exists():
            sys.exit(f"нет обязательного файла: {f}")
        out.append(p)
    return out


def assert_clean(files: list[Path]) -> None:
    bad = [p.as_posix() for p in files if p.name in SECRET_BASENAMES]
    if bad:
        sys.exit(f"сборка остановлена, в бандл попали секреты: {bad}")


def load_manifest(version: str) -> dict:
    if not MANIFEST_SRC.exists():
        sys.exit(f"манифест не найден: {MANIFEST_SRC}")
    manifest = json.loads(MANIFEST_SRC.read_text(encoding="utf-8"))
    # Версия живёт в pyproject.toml: манифест подтягиваем к ней, чтобы релиз
    # физически не мог уехать с расхождением.
    if manifest.get("version") != version:
        print(f"  (версия манифеста {manifest.get('version')} → {version})")
        manifest["version"] = version
    return manifest


def build(list_contents: bool) -> Path:
    version = read_field("version")
    name = read_field("name")
    manifest = load_manifest(version)
    files = collect_runtime()
    assert_clean(files)

    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / f"{name}-v{version}.mcpb"
    if out.exists():
        out.unlink()

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo("manifest.json")
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = (0o100000 | 0o644) << 16
        zf.writestr(info, json.dumps(manifest, ensure_ascii=False, indent=2))
        for p in files:
            rel = p.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo.from_file(p, f"server/{rel}")
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100000 | zip_mode(p)) << 16
            zf.writestr(info, p.read_bytes())

    print(f"\nСобрано {out.relative_to(ROOT)} "
          f"({len(files) + 1} записей, {out.stat().st_size / 1024:.0f} КБ)")
    if list_contents:
        with zipfile.ZipFile(out) as zf:
            for n in sorted(zf.namelist()):
                print(f"  {n}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="показать содержимое после сборки")
    build(ap.parse_args().list)


if __name__ == "__main__":
    main()
