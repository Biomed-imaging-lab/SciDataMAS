# Архитектура SciDataMAS DSH

[English](ARCHITECTURE.md) · **Русский**

Документ для разработчика: как плагин встроен в DSH, какие инварианты держит, где расширять.

## 1. Интеграция с DSH

Плагин — обычный Cordis-пакет:

```js
export const name = 'scidatamas'
export const inject = ['tools', 'systemPrompt']
export const Config = z.object({ ... })
export async function apply(ctx, config) { ... }
```

- `ctx.tools.register(defineTool(...))` регистрирует 11 инструментов; схемы аргументов и output-контракт проверяются DSH.
- `ctx.systemPrompt.section({ name: 'tool:scidatamas', order: 150, text })` добавляет агенту правила работы с озером.
- `ctx.llm.stream(...)` — единственный путь к модели. Маршрут по умолчанию — `exec.agent.model.current()`; fallback — `config.provider/model`, затем `ctx.agentDefaultModel`.
- `ctx.workingDirectory` не используется: корень озера задаётся конфигом, а не текущей директорией сессии, чтобы данные не «переезжали» между сессиями.
- Плагин регистрирует инструменты везде; в Web-профиле дополнительно регистрируются HTTP API только для чтения и клиентский bundle. Headless-композиция остаётся только с инструментами.

`package.json` объявляет bundle:

```json
"dsh": { "bundle": { "patch": "./cordis.patch.yml" } }
```

`cordis.patch.yml` вставляет одну строку `scidatamas`. Пользователь переопределяет её конфиг в профиле по `id: scidatamas`.

### Почему bundle, а не набор отдельных плагинов

Сервис, workflow и инструменты делят один `SciDataMAS`-инстанс (озеро + LLM-клиент + аудит). Дробить их на строки композиции без необходимости значит плодить межплагинные зависимости и риск двух озер в одном профиле. Одна строка проще для установки и HMR.

### Модель и аудит

Внутренние вызовы не являются частью диалога, но должны быть воспроизводимы. Поэтому `LlmClient`:

- передаёт `system` и `messages` в `ctx.llm.stream`;
- собирает `BlockAssembler`;
- проверяет терминальный `finish` (`error`/`aborted` → исключение);
- пишет запись в `logs/llm-calls.jsonl`: `ts`, `purpose`, `provider`, `model`, `duration_ms`, `usage`, `finish`, `system`, `messages`, `response`, `error`.

Запись обрезается по `logMaxChars` (по умолчанию 200k символов на поле). Это не session log DSH, а отдельный audit log озера; он переживает сессию и лежит рядом с данными. Если политика требует строгого «model-visible ⟺ session log», можно добавить событие в session через `ctx.on`/`session.append`; текущая версия сознательно не раздувает историю диалога гигантскими DAG-промптами.

## 2. Слои

```text
tools.js            модельные контракты, описания, рендер
  ↓
service.js          фасад: init, create, validate, add, query, import
  ↓
workflows/*.js      бизнес-процессы, prompts, LLM-вызовы
  ↓
lake.js             каталог, манифесты, metadata.jsonl, staging, events
  ↓
storage.js          StorageBackend (local сегодня; s3/synology — extension points)
```

`metadata.js`, `inspect.js`, `filter.js`, `util.js` — детерминированные утилиты без DSH-зависимостей. Благодаря этому 31 тестов гоняются обычным `node --test` без профиля.

## 3. Состояния датасета

```text
create ──► draft ──(update status=active | commit add)──► active ──► archived
              │
              └── validate_schema: schema_version помечается validated,
                  но сама схема не меняется
```

Инварианты:

- `schema_version` увеличивается только при реальном изменении пользовательских полей.
- `validated_schema_version` сбрасывается при изменении схемы.
- `status` меняется только явным `update_dataset` или успешным коммитом данных.
- Удаление полей требует `allow_removals=true`.
- Схема всегда содержит системные поля; пользовательские поля не могут занимать их имена.

## 4. Манифест датасета

```json
{
  "id": "confocal_cells_2026",
  "name": "Confocal cells 2026",
  "description": "...",
  "purpose": "...",
  "layout": "files",
  "status": "draft",
  "modality": "microscopy",
  "provenance": "real",
  "author": "A. Sachuk",
  "created_at": "...",
  "updated_at": "...",
  "schema_version": 1,
  "validated_schema_version": null,
  "schema": {
    "fields": [
      { "name": "id", "type": "string", "system": true, "required": true },
      { "name": "pixel_size_nm", "type": "number", "description": "...", "required": true }
    ],
    "rejected": [],
    "warnings": []
  },
  "table": null,
  "source": null,
  "counts": { "records": 0, "files": 0, "bytes": 0 },
  "defaults": { "author": "...", "uploaded_at": "..." },
  "storage": { "driver": "local", "root": "local://" }
}
```

Для table-датасета `table` содержит `path`, `row_key`, `row_key_fallback`, `columns` (с `source`), `row_count`, `format`, `size`. Схема содержит поля `scope: "column"` с `source` — исходным именем колонки, если нормализация изменила имя.

## 5. Потоки

### 5.1 Single-call

```text
tool args ──► inspect examples ──► prompt ──► llm.json ──► normalizeSchema
                                                   │
                                                   └──► createDataset
```

Если `layout=table`, вместо общего single-call используется `tableSchemaSystem` + досье таблицы; затем `registerTable` копирует таблицу и добавляет недостающие колонки в схему.

### 5.2 DAG

```text
description ──► planDag ──► validateDag ──(bad)──► repair call
                                  │(ok)
                                  ▼
                    per-node field generation (bounded concurrency)
                                  │
                                  ▼
                    merge + node_id/node_description + normalize
```

Валидатор проверяет:

- уникальные id, допустимые типы `entity|signal|derivative`;
- `preparation`: entity→entity; `capture`: entity→signal; `program`: signal/derivative→derivative;
- ацикличность (Kahn);
- наличие хотя бы одного signal/derivative;
- лимит `maxDagNodes`.

Параллельные per-node вызовы не видят поля друг друга (кроме снимка `existingNames` на момент старта), поэтому возможны дубликаты. Они схлопываются по имени с предупреждением; это осознанный trade-off скорость/полнота.

### 5.3 Дебат

```text
for run in 1..N:
  scenario+roles (no schema)
  parallel: role questions
  owner answers (exact schema)
  score fields, collect unanswered
aggregate:
  coverage, useful fields, unused fields, dedup unanswered
synthesis:
  clarifications + suggested fields
persist validation/latest.json, mark schema validated
```

Оценка намеренно асимметрична: роли не видят схему, владелец видит только схему. Это ловит поля, которые «есть в схеме, но не отвечают на реальные вопросы», и вопросы, на которые метаданных не хватает. Владелец не может выдумать поле: `validFields` фильтруются по точному набору имён, иначе ответ считается неотвеченным + warning.

### 5.4 Stage/commit

```text
collect files ──► inspect ──► fill batches (LLM) ──► merge explicit
                                                   │
                                                   ▼
                                      partial validation + missing
                                                   │
                              ready? ──no──► return stage (no copy)
                                 │yes
                                 ▼
                    strict validation of all records
                                 │
                                 ▼
                    copy files ──► append metadata ──► event ──► active
```

Копирование начинается только после того, как все записи прошли строгую валидацию. Это не транзакция на уровне ФС: если копирование упадёт на середине, часть файлов останется. Для production-версии нужен staging-then-rename на уровне датасета или манифест транзакции; отмечено в roadmap.

### 5.5 Retrieval

```text
query ──► select dataset (LLM / lexical) ──► plan filter (LLM)
      ──► validateFilter ──► runQuery ──► resolve files/previews
```

Фильтр — JSON DSL, не SQL. Это убирает целый класс атак и позволяет валидировать поля до исполнения. При ошибке планировщика используется лексический ранжировщик, а не «пустой результат».

### 5.6 Внешний импорт

```text
url ──► parse (Zenodo/DOI/URL) ──► analyze (API + file list)
                                 │
                    mode=analyze └──► return plan
                                 │mode=import
                                 ▼
                  download to _imports/<id> (limits, globs)
                                 ▼
                  inspect ──► create/choose dataset ──► map record metadata
                                 ▼
                  stage ──► commit ──► event ──► delete staging on success
```

Zenodo API отдаёт `files[].links.self` (часто `/api/records/<id>/files/<key>/content`), что и используется для скачивания. Для прямого URL — HEAD; если сервер не поддерживает HEAD, стоит добавить fallback на GET (roadmap).

## 6. Табличные данные: почему sidecar

Альтернативы, которые рассматривались:

| Вариант | Плюсы | Минусы |
|---|---|---|
| Хранить JSON-блоб метаданных в схеме | просто | не масштабируется, ломает табличный формат, трудно фильтровать |
| Дублировать CSV с добавленными колонками | привычно | две копии данных, рассинхронизация, большой объём |
| Строка/id из CSV + sidecar JSONL | таблица канонична, row-метаданные добавляются частями, фильтры по обоим слоям | нужен row key и merge при выдаче |

Выбран третий. `row_key` определяется так: явный `row_key` → колонки `id/row_id/row/index/sample_id/key` с уникальными непустыми значениями → первая уникальная колонка → `__row_index__` (индекс строки). Если уникальность теряется, `row_key_fallback=true`; id строк становятся позиционными и нестабильны при переупорядочивании таблицы — это фиксируется в манифесте.

## 7. Расширение хранилища

`StorageBackend` намеренно маленький и без «умных» операций. Для S3:

- `readText/writeText/readBuffer/writeBuffer` → `GetObject/PutObject`;
- `copyIn` → `PutObject` из файла (stream);
- `list(prefix)` → `ListObjectsV2` с пагинацией;
- `localPath(key)` → путь в materialization-кэше (скачать при необходимости);
- `uri(key)` → `s3://bucket/key`.

Каталог (`catalog.json`, манифесты) можно оставить в локальном control plane или перенести в БД; ключи уже относительные. Для Synology разумный первый шаг — смонтированный SMB/WebDAV и `LocalStorage`; нативный клиент — тот же интерфейс.

Что нужно добавить перед реальным remote:

- кэш materialization и инвалидация;
- транзакционность манифеста и metadata при сетевых сбоях;
- распределённая блокировка каталога;
- проверка целостности (размер/хеш) после записи.

## 8. Обработка ошибок

- `LakeError` с кодом (`SCIDATAMAS_NOT_FOUND`, `SCIDATAMAS_MISSING_FIELDS`, ...) — ожидаемые доменные ошибки; текст пригоден для пользователя.
- `ModelError` с кодом (`SCIDATAMAS_NO_MODEL`, `SCIDATAMAS_BAD_JSON`, ...) — проблемы маршрута/ответа.
- `defineTool` сам валидирует аргументы; исключения инструмента становятся error-результатом, а не падением сессии.
- `exec.signal` пробрасывается в LLM и HTTP; длинные инструменты объявляют `timeoutMs`.
- Битый манифест одного датасета не блокирует `list_datasets` (ошибки чтения пропускаются), но `get_data` по нему вернёт ошибку.

## 9. Проверка в DSH

1. `node --test test/*.test.js` — 31 тестов без DSH.
2. Smoke-регистрация: импортировать `src/index.js`, вызвать `apply` с минимальным fake-ctx (`tools.register`, `systemPrompt.section`) и проверить 11 инструментов.
3. Загрузка в реальном профиле:

```bash
export DSH_HOME=/path/to/test-home
dsh --profile scitest --from-default-profile headless --dump-config
# добавить строку scidatamas в cordis.patch.yml
dsh --profile scitest --dump-config-schema | grep scidatamas
```

`--dump-config-schema` импортирует модуль и читает `Config`, не выполняя модель. Для полного прогона нужен ключ провайдера и сессия.

## 10. Web-панель

Панель — вторая (браузерная) половина того же пакета. Хост-половина и клиентская половина не делят код: хост отдаёт API, клиент рисует UI.

### 10.1. Как клиент попадает в браузер

`package.json` объявляет:

```json
"exports": { "./client": "./src/client.js" },
"dsh": {
  "bundle": { "patch": "./cordis.patch.yml" },
  "client": { "platform": "web" }
}
```

`dsh-client-modules` сканирует активные Loader-строки, читает `dsh.client`, собирает boot graph и отдаёт `src/client.js` как bundle под `/plugins`. Формат файла — не обычный ESM, а фабрика модульного загрузчика:

```js
window.__ModuleLoader__.load({
  id: 'scidatamas-dsh-plugin',
  factory: (require) => {
    const React = require('react')
    ...
    exports.apply = apply
    return module.exports
  }
})
```

React, `react/jsx-runtime` и сервисы (`ctx.slots`, `ctx.locale`) входят в platform seed; поэтому bundle не тянет свои зависимости и не требует сборки. Это осознанный выбор для плагина-«коробки»: `src/client.js` читается и правится как обычный файл, `pnpm run build` не нужен. Если панель вырастет, её можно перевести на TS/tsdown, не меняя контракт `dsh.client`.

### 10.2. Слоты

Клиентский `apply(ctx)`:

```js
ctx.effect(() => ctx.locale.register('scidatamas', { en, ru }), '...')
const t = ctx.locale.bind('scidatamas')

ctx.slots.inject('main', () => ctx.slots.register({
  name: 'main', key: 'scidatamas', locale: 'scidatamas',
}, Page))

ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({
  name: 'sidebar.panellist', id: 'scidatamas', order: 20,
  locale: 'scidatamas', label: () => t('panel'),
}, DataIcon))
```

`sidebar.panellist` добавляет строку в левую панель; клик вызывает `layout.selectPanel('scidatamas')`. `main` с тем же `key` — сама страница. `slots.inject` ждёт объявления слота и снимает регистрацию при выгрузке плагина. `ctx.locale` даёт словари en/ru.

### 10.2.1. Режим «рядом с чатом»

Та же страница зарегистрирована как page-type правого sidebar `scidatamas-data` (`ctx.sidebarRightTabs.register`) с body в слоте `sidebar.right.pane.tab`. Кнопка **Открыть рядом с чатом** переключает main обратно на диалог (`layout.selectPanel(null)`) и открывает страницу через `ctx.sidebarRight.openTab('scidatamas-data')`. Тип также добавляет карточку в guide, поэтому его можно открыть из кнопки добавления правого sidebar. Компактная раскладка меняет grid на «список сверху, детали снизу» для узкой колонки.

Вкладка **Content** запрашивает `/datasets/<id>/content?limit=&offset=` и рисует полученный порядок колонок и строки как прокручиваемую таблицу. **Скачать CSV** ведёт на тот же endpoint с `format=csv`, который отдаёт `text/csv` как attachment. Кнопка «Показать ещё» управляется полем `has_more`.

### 10.3. API и авторизация

`src/web-api.js` регистрирует prefix-route `/scidatamas/api` на `webServer` и проверяет:

```js
const admission = connection.admit(req)
if (admission.rejection) → 401/403
if (admission.peer.principal.kind !== 'owner') → 403
```

То есть панель доступна только тому же owner-peer, что и остальной Web GUI; отдельного токена/логина нет. Route регистрируется только если в профиле есть `webServer` и `connection` (Web), поэтому headless-профиль не открывает HTTP-порт.

Эндпоинты:

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/scidatamas/api/status` | root, storage, число датасетов, доступность модели, лимиты |
| GET | `/scidatamas/api/datasets?query=` | каталог |
| GET | `/scidatamas/api/datasets/<id>` | детали: схема, samples, validation summary, events |
| GET | `/scidatamas/api/datasets/<id>/content?limit=&offset=` | постраничные строки метаданных для вкладки **Content** |
| GET | `/scidatamas/api/datasets/<id>/content?format=csv` | те же строки в виде скачиваемого CSV |
| GET | `/scidatamas/api/datasets/<id>/validation` | полный отчёт валидации |
| GET | `/scidatamas/api/datasets/<id>/file?path=` | артефакт из `datasets/<id>/files/...` |

Отдача файлов:

- принимается только ключ внутри `datasets/<id>/files/`;
- `..` и абсолютные ключи отсекаются и проверкой префикса, и `StorageBackend`;
- `Content-Type` из расширения, `Content-Disposition: inline` для изображений/текста/PDF, иначе `attachment`;
- `X-Content-Type-Options: nosniff`; HTML/JS артефакты не исполняются в контексте GUI;
- для remote-бэкенда нужен materialization-кэш, сейчас возвращается 501.

### 10.4. Тема

У панели нет собственной палитры. Она использует алиасы темы DSH (`--dsw-alias-bg-base`, `--dsw-alias-bg-layer-2/3`, `--dsw-alias-label-*`, `--dsw-alias-border-*`, state-цвета) и системные цвета CSS как fallback (`Canvas`, `CanvasText`, `ButtonFace`, `Field`, `GrayText`). `color-scheme: light dark` держит нативные поля и focus ring в тон активной теме. Раньше использовались опечатанные алиасы `--dsw-alias-bg-l1` / `fill-l1`, которые молча падали в белый и давали белый текст на белом фоне в тёмной теме; теперь `test/theme.test.js` проверяет реальные имена токенов.

### 10.5. Почему read-only

Запись из панели означала бы второй путь создания/добавления данных в обход staging, строгой валидации и подтверждения. В первой версии панель — окно наблюдения: каталог, схема, validation, samples, events. Все изменения идут через инструменты агента, где работает аудит и human-in-the-loop. Следующий этап — добавить из панели безопасные действия: activate, редактирование описания/схемы, запуск debate, commit готового stage; каждое действие должно вызывать те же workflow-функции, а не писать в озеро напрямую.

### 10.6. Проверка

- `test/web-api.test.js` поднимает реальный `node:http` сервер и проверяет статус, каталог, детали, отдачу файла, запрет traversal и 401 для не-owner.
- Регистрация клиентского bundle проверяется smoke-скриптом (подмена `window.__ModuleLoader__` и React), а в живом Web-профиле — загрузкой страницы: в boot graph присутствует `scidatamas-dsh-plugin/client.js`, панель **Data** появляется в sidebar.
- UI проверен headless Chromium (Playwright): каталог, Schema, Validation, Samples, Events; скриншоты лежат в `docs/assets/`.

## 11. Roadmap

1. S3/Synology backends + materialization cache.
2. Действия из Web-панели: activate, правка описания/схемы, запуск debate, commit stage.
3. Гармонизация схем между датасетами (top-k + LLM, как в статье).
4. Добавление новых строк в table-датасет (append + пересчёт row key).
5. Parquet/Excel/HDF5-инспекция.
6. Транзакционный commit (staging dir → atomic rename).
7. Пагинация/курсоры для больших выборок.
8. Сессионные события для LLM-вызовов (строгий model-visible ⟺ session log).
9. Дедупликация импорта по checksum.
10. Экспорт в RO-Crate/BIDS-подобные форматы.
