"""Инвентаризация сценария Make по выгрузке (Scenario → … → Export Blueprint) — до начала переноса.

    python inventory.py blueprint.json [ещё.json ...]

Показывает, что придётся переносить: модули и сервисы, роутеры и фильтры, функции в формулах,
внешние адреса и — отдельно — похожие на секреты строки (токены в URL, ключи), которые нельзя
переносить «как есть» и нельзя коммитить. По этому списку оценивается объём и цена переноса.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

FUNC_RE = re.compile(r"\b([a-zA-Z]+)\(")
REF_RE = re.compile(r"\{\{[^}]*\}\}")
URL_RE = re.compile(r"https?://[^\s\"'{}]+")
SECRET_RES = [
    (re.compile(r"bot\d{6,}:[A-Za-z0-9_-]{30,}"), "токен Telegram-бота в URL"),
    (re.compile(r"\b(sk|pk|rk)[-_][A-Za-z0-9-]{16,}"), "API-ключ"),
    (re.compile(r"(?i)(api[_-]?key|token|secret|password)\W{0,3}[:=]\W{0,3}[A-Za-z0-9._-]{12,}"), "ключ/пароль в тексте"),
]
# Функции Make, у которых в JavaScript/n8n есть ловушка при переносе (проверено тестами этого проекта)
PITFALLS = {
    "ifempty": "в JS → `x || 'y'`, НЕ `x ?? 'y'`: ifempty считает пустую строку пустой",
    "trim": "в JS `.trim()` падает на отсутствующем поле → `String(x ?? '').trim()`",
    "replace": "регулярка в Make — строка в кавычках \"/re/g\"; в JS — литерал /re/g",
}
OPERATOR_PITFALLS = {
    "exist": "фильтр «существует» в Make считает пустую строку несуществующей → в n8n `is not empty`, не `exists`",
    "notexist": "то же, обратное → в n8n `is empty`",
}


def load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    # Три формата: файл «Export Blueprint» из интерфейса — сам blueprint;
    # API шаблонов — {"blueprint": …}; API сценария — {"code": "OK", "response": {"blueprint": …}}
    data = data.get("response", data)
    return data.get("blueprint", data)


def walk(flow, depth=0):
    for m in flow:
        yield m, depth
        for route in m.get("routes") or []:
            yield from walk(route.get("flow", []), depth + 1)


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def report(path: Path) -> None:
    bp = load(path)
    modules = list(walk(bp.get("flow", [])))
    apps = Counter(m["module"].split(":")[0] for m, _ in modules)
    funcs, operators, urls, secrets, routers, filters = Counter(), Counter(), set(), [], 0, 0

    for m, _ in modules:
        if m.get("routes"):
            routers += 1
        f = m.get("filter")
        if f:
            filters += 1
            for group in f.get("conditions", []):
                for c in group:
                    operators[c.get("o")] += 1
        for s in strings(m.get("mapper")) if m.get("mapper") else []:
            for ref in REF_RE.findall(s):
                funcs.update(fn for fn in FUNC_RE.findall(ref))
            urls.update(URL_RE.findall(s))
            for rx, label in SECRET_RES:
                if rx.search(s):
                    secrets.append(f"модуль {m['id']} ({m['module']}): {label}")

    print(f"\n=== {bp.get('name', path.name)}  [{path.name}]")
    print(f"Модулей: {len(modules)}, роутеров: {routers}, фильтров: {filters}, "
          f"мгновенный запуск (вебхук): {'да' if bp.get('metadata', {}).get('instant') else 'нет'}")
    print("Сервисы:", ", ".join(f"{a} ×{n}" for a, n in apps.most_common()))
    print("Модули:")
    for m, depth in modules:
        name = (m.get("filter") or {}).get("name")
        print("  " + "  " * depth + f"{m['id']}: {m['module']}" + (f"   [фильтр: {name}]" if name else ""))
    if funcs:
        print("Функции в формулах:", ", ".join(f"{f} ×{n}" for f, n in funcs.most_common()))
    if operators:
        print("Операторы фильтров:", ", ".join(f"{o} ×{n}" for o, n in operators.most_common()))
    hosts = sorted({re.sub(r"(bot)\d+:[^/]+", r"\1<TOKEN>", u.split("?")[0]) for u in urls})
    if hosts:
        print("Внешние адреса:", *hosts, sep="\n  ")
    notes = [f"  {f}(): {PITFALLS[f]}" for f in funcs if f in PITFALLS]
    notes += [f"  фильтр {o}: {OPERATOR_PITFALLS[o]}" for o in operators if o in OPERATOR_PITFALLS]
    if notes:
        print("⚠️ Ловушки при переносе:", *notes, sep="\n")
    if secrets:
        print("🔐 Секреты в сценарии (в n8n — только через Credentials, в git — никогда):", *secrets, sep="\n  ")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for p in sys.argv[1:]:
        report(Path(p))
