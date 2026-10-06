# make-to-n8n

Демо переноса сценария из **Make.com** на собственный **n8n** — с доказательством, что новый сценарий
работает так же, как старый.

**Что внутри:**
- исходный сценарий Make «Заявка → Telegram» (вебхук → роутер с фильтрами → Telegram → ответ на вебхук),
  создан через Make API (`make_setup.py`);
- тот же сценарий в n8n (`n8n/workflow.json`);
- 7 тестовых заявок с подвохами (пустые и отсутствующие поля, кавычки, переносы строк) — `tests/cases.json`;
- сравнение ответов старого и нового сценария — `tests/compare.py`: **7 из 7 совпадают**;
- «наивный» перенос для сравнения (`n8n/workflow_naive.json`) — **2 тихие ошибки из 7**: тест их ловит;
- `inventory.py` — разбор выгрузки сценария Make перед переносом: модули, сервисы, функции, ловушки, зашитые секреты.

Главный документ — [MIGRATION.md](MIGRATION.md): таблица соответствий Make → n8n и ловушки, каждая подтверждена тестом.

## Запуск
Только стандартная библиотека Python, зависимостей нет.
```bash
python inventory.py make/blueprint.json             # разбор сценария Make
python tests/run_cases.py make                      # эталон: ответы Make → tests/results_make.json
python tests/run_cases.py n8n                       # ответы n8n → tests/results_n8n.json
python tests/compare.py                             # сравнение
python tests/compare.py make n8n_naive              # наивный перенос — видно расхождения
```
Для `make_setup.py` (создать исходный сценарий в своём Make) — `.env`: `MAKE_API_TOKEN`, `MAKE_ZONE`,
`TG_BOT_TOKEN`, `TG_CHAT_ID`. n8n — локальный, импорт через CLI контейнера:
```bash
docker cp n8n/workflow.json <контейнер>:/tmp/wf.json
docker exec <контейнер> n8n import:workflow --input=/tmp/wf.json
docker exec <контейнер> n8n update:workflow --id=mkMigratedLead01 --active=true
docker restart <контейнер>
```
В Git Bash на Windows — с `MSYS_NO_PATHCONV=1`, иначе путь `/tmp/...` превратится в виндовый.
