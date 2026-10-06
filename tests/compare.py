"""Сравнивает ответы старого (Make) и нового (n8n) сценария на одинаковых заявках.

    python tests/compare.py                 # results_make.json vs results_n8n.json
    python tests/compare.py make n8n_naive  # любые два прогона
Код выхода 1, если есть расхождения.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent


def main():
    a, b = (sys.argv[1:3] if len(sys.argv) >= 3 else ("make", "n8n"))
    ra = json.loads((HERE / f"results_{a}.json").read_text(encoding="utf-8"))
    rb = json.loads((HERE / f"results_{b}.json").read_text(encoding="utf-8"))
    diffs = 0
    for name, exp in ra.items():
        got = rb.get(name)
        same = got is not None and got["status"] == exp["status"] and got["body"].strip() == exp["body"].strip()
        print(("✅" if same else "❌"), name)
        if not same:
            diffs += 1
            print(f"   {a}: {exp['status']} {exp['body']!r}")
            print(f"   {b}: {got['status'] if got else '—'} {got['body']!r}" if got else f"   {b}: нет ответа")
    print(f"\n{len(ra) - diffs} из {len(ra)} совпадают" + ("" if not diffs else f", расхождений: {diffs}"))
    sys.exit(1 if diffs else 0)


if __name__ == "__main__":
    main()
