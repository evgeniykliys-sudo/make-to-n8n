"""Создаёт в Make исходный сценарий «Заявка → Telegram» через Make API (то, что потом переносим в n8n).

    python make_setup.py

Сценарий: Custom webhook → Router
  ├─ [фильтр: phone есть]   → HTTP: Telegram sendMessage → Webhook response 200 (текст сообщения)
  └─ [фильтр: phone нет]    → Webhook response 422

Пишет make/state.json (id вебхука, сценария, URL) и make/blueprint.json (без токена бота).
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
ENV = dict(l.split("=", 1) for l in (ROOT / ".env").read_text(encoding="utf-8").splitlines() if "=" in l)
ZONE = ENV["MAKE_ZONE"].rstrip("/")
TOKEN = ENV["MAKE_API_TOKEN"]
TEAM_ID = int(ENV.get("MAKE_TEAM_ID", "3075420"))
TG_TOKEN = ENV["TG_BOT_TOKEN"]
TG_CHAT = ENV["TG_CHAT_ID"]

# Текст сообщения — формулы Make (IML). Строковые аргументы и регулярка — В КАВЫЧКАХ:
# без них Make отвергает сценарий («Unexpected [», «Operator on end of an expression»).
TEXT = (
    "🆕 Новая заявка\n"
    "Имя: {{trim(1.name)}}\n"
    'Телефон: {{replace(1.phone; "/[^0-9+]/g"; emptystring)}}\n'
    'Сообщение: {{ifempty(1.message; "—")}}\n'
    'Источник: {{ifempty(1.source; "сайт")}}'
)


def api(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"{ZONE}/api/v2{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Token {TOKEN}", "Content-Type": "application/json",
                 "User-Agent": "make-to-n8n-demo/1.0 (+github.com/evgeniykliys-sudo)"},  # без него Cloudflare отвечает 403 / 1010
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} → {e.code}: {e.read().decode()[:800]}")


def blueprint(hook_id: int, tg_token: str) -> dict:
    def md(x, y):
        return {"designer": {"x": x, "y": y}}

    return {
        "name": "Заявка → Telegram (исходный, Make)",
        "flow": [
            {"id": 1, "module": "gateway:CustomWebHook", "version": 1,
             "parameters": {"hook": hook_id, "maxResults": 1}, "mapper": {}, "metadata": md(0, 0)},
            {"id": 2, "module": "builtin:BasicRouter", "version": 1, "mapper": None, "metadata": md(300, 0),
             "routes": [
                 {"flow": [
                     # Формат mapper — как в публичных шаблонах Make (снято через /templates/public/*/blueprint).
                     # Telegram sendMessage — GET с параметрами в строке запроса: Make сам их URL-кодирует
                     # (кавычки и переносы строк в тексте заявки не ломают запрос, в отличие от сырого JSON).
                     {"id": 3, "module": "http:ActionSendData", "version": 3,
                      "parameters": {"handleErrors": False},
                      "filter": {"name": "Есть телефон", "conditions": [[{"a": "{{1.phone}}", "o": "exist"}]]},
                      "mapper": {
                          # Только непустые поля: текущая валидация Make отвергает пустые строки в типизированных
                          # полях (timeout, contentType…), хотя старые публичные шаблоны их содержат.
                          "url": f"https://api.telegram.org/bot{tg_token}/sendMessage",
                          "method": "get", "headers": [],
                          # Обязательны в текущей версии модуля (в старых публичных шаблонах useMtls ещё нет):
                          "serializeUrl": False, "useMtls": False,
                          "bodyType": "raw", "contentType": "application/json", "data": "",
                          "ca": "", "timeout": "", "authUser": "", "authPass": "",
                          "qs": [{"name": "chat_id", "value": TG_CHAT}, {"name": "text", "value": TEXT}],
                          "gzip": True, "shareCookies": False, "parseResponse": True, "followRedirect": True,
                          "useQuerystring": False, "followAllRedirects": False, "rejectUnauthorized": True,
                      },
                      "metadata": md(600, -150)},
                     {"id": 4, "module": "gateway:WebhookRespond", "version": 1, "parameters": {},
                      "mapper": {"status": "200", "body": TEXT},
                      "metadata": md(900, -150)},
                 ]},
                 {"flow": [
                     {"id": 5, "module": "gateway:WebhookRespond", "version": 1, "parameters": {},
                      "filter": {"name": "Нет телефона", "conditions": [[{"a": "{{1.phone}}", "o": "notexist"}]]},
                      "mapper": {"status": "422", "body": "Заявка без телефона — не отправлена"},
                      "metadata": md(600, 150)},
                 ]},
             ]},
        ],
        "metadata": {
            "instant": True, "version": 1,
            "scenario": {"roundtrips": 1, "maxErrors": 3, "autoCommit": True, "autoCommitTriggerLast": True,
                         "sequential": False, "confidential": False, "dataloss": False, "dlq": False,
                         "freshVariables": False},
            "designer": {"orphans": []},
        },
    }


def main():
    out = ROOT / "make"
    out.mkdir(exist_ok=True)
    state_path = out / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}

    if "hook_id" not in state:
        hook = api("POST", "/hooks", {"name": "lead-demo", "teamId": TEAM_ID, "typeName": "gateway-webhook",
                                      "method": False, "headers": False, "stringify": False})["hook"]
        state.update(hook_id=hook["id"], hook_url=hook["url"])
        print("Вебхук:", hook["url"])

    bp = blueprint(state["hook_id"], TG_TOKEN)
    if "scenario_id" in state:
        api("PATCH", f"/scenarios/{state['scenario_id']}?confirmed=true", {"blueprint": json.dumps(bp, ensure_ascii=False)})
        print("Сценарий обновлён:", state["scenario_id"])
    else:
        sc = api("POST", "/scenarios?confirmed=true", {
            "blueprint": json.dumps(bp, ensure_ascii=False), "teamId": TEAM_ID,
            "scheduling": json.dumps({"type": "immediately"}),
        })["scenario"]
        state["scenario_id"] = sc["id"]
        print("Сценарий создан:", sc["id"])
    # Make отключает сценарий при ошибке инициализации; уже активный повторно «стартовать» нельзя (IM306)
    if not api("GET", f"/scenarios/{state['scenario_id']}")["scenario"].get("isActive"):
        api("POST", f"/scenarios/{state['scenario_id']}/start")
    print("Сценарий активен")

    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    # В репозиторий — без токена бота
    (out / "blueprint.json").write_text(
        json.dumps(blueprint(state["hook_id"], "<BOT_TOKEN>"), ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
