"""Шлёт тестовые заявки (tests/cases.json) в вебхук и сохраняет ответы.

    python tests/run_cases.py make   → tests/results_make.json
    python tests/run_cases.py n8n    → tests/results_n8n.json
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
URLS = {
    "make": lambda: json.loads((ROOT / "make" / "state.json").read_text())["hook_url"],
    "n8n": lambda: "http://localhost:5678/webhook/lead-migrated",
    "n8n_naive": lambda: "http://localhost:5678/webhook/lead-naive",  # демонстрация ошибок буквального переноса
}


def send(url: str, body: dict) -> tuple[int, str]:
    req = urllib.request.Request(
        url, data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "make-to-n8n-demo/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main():
    target = sys.argv[1]
    url = URLS[target]()
    cases = json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))
    only = sys.argv[2:]  # можно передать номера кейсов
    results = {}
    for c in cases:
        if only and not any(c["name"].startswith(n + ".") for n in only):
            continue
        code, body = send(url, c["body"])
        results[c["name"]] = {"status": code, "body": body}
        print(f"=== [{target}] {c['name']} -> {code}\n{body}\n")
    out = Path(__file__).parent / f"results_{target}.json"
    if not only:
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
