# Справочник инструментов

[English](TOOLS.md) · **Русский**

Все инструменты имеют префикс `scidatamas_`. Аргументы валидируются DSH до выполнения; ошибки возвращаются как error-результат, а не обрывают сессию. Длинные операции объявляют `timeoutMs` и слушают `exec.signal`.

## `scidatamas_create_dataset`

Создать датасет с компактной схемой (single-call).

| Аргумент | Тип | Обяз. | Смысл |
|---|---|---|---|
| `name` | string | да | имя; из него делается id |
| `description` | string | да | что содержит датасет и что такое одна строка |
| `purpose` | string | нет | планируемое использование; влияет на поля и дебат |
| `layout` | `files` \| `table` | нет | по умолчанию `files` |
| `table_path` | string | для table | CSV/TSV/JSON/JSONL |
| `row_key` | string | нет | колонка-идентификатор строки |
| `example_paths` | string[] | нет | файлы/каталоги только как evidence, не копируются |
| `author` | string | нет | автор по умолчанию |
| `modality` | string | нет | например `microscopy` |
| `tags` | string[] | нет | теги |
| `activate` | boolean | нет | сразу active (по умолчанию draft) |
| `validate` | boolean | нет | сразу запустить дебат |
| `debate_runs` | integer | нет | прогонов при `validate=true` |

Возвращает: `dataset` (summary), `schema` (с системными полями), `system_fields`, `generated`, `evidence`, `table`, `validation`, `next_steps`.

Ошибки: пустое имя/описание, `layout=table` без `table_path`, дубликат id, пустая схема от модели, отсутствие модели.

## `scidatamas_create_dataset_dag`

То же, но rich-режим: DAG-планирование, валидация топологии, генерация полей по узлам.

Возвращает дополнительно `generated.dag`, `generated.dag_text`, `generated.warnings`, `generated.nodes`, `generated.fields`. Поля схемы содержат `node_id`/`node_description`.

Когда использовать: многостадийный эксперимент, пользователь просит «богатую/подробную разметку», данные будут автоматически аннотироваться пайплайном. Когда не использовать: небольшой плоский датасет, важна читаемость и минимум лишних полей.

## `scidatamas_validate_schema`

| Аргумент | Тип | Обяз. | Смысл |
|---|---|---|---|
| `dataset_id` | string | да | датасет |
| `runs` | integer | нет | 1–5, по умолчанию 3 |

Возвращает:

- `coverage` — доля пользовательских полей, реально использованных при ответах;
- `useful_fields[]` — `{name, uses, runs_used, description, type}`;
- `unused_fields[]` — поля, которые не понадобились ни одному ревьюеру;
- `unanswered_questions[]` — `{text, count, roles, runs}`;
- `clarifications[]` — `{question, why, asked_in_runs, suggested_field}`;
- `suggested_fields[]` — готовые к добавлению поля;
- `run_details[]` — сценарий, роли, число вопросов/ответов;
- `report_path` — `datasets/<id>/validation/latest.json`.

Схема не изменяется. `validated_schema_version` становится равным текущей `schema_version`. Если схема потом изменится, маркер сбросится.

## `scidatamas_update_dataset`

| Аргумент | Тип | Смысл |
|---|---|---|
| `dataset_id` | string | да |
| `name`, `description`, `purpose`, `author` | string | новые значения |
| `fields` | json | полная замена пользовательских полей; системные добавляются сами |
| `status` | `draft` \| `active` \| `archived` | статус |
| `tags` | string[] | замена тегов |
| `allow_removals` | boolean | подтвердить удаление полей |

При изменении схемы `schema_version++`, `validated_schema_version=null`. Без `allow_removals=true` удаление существующих полей отклоняется.

## `scidatamas_list_datasets`

`query` (string, необязательный), `include_drafts` (boolean, по умолчанию true). Возвращает `{root, datasets:[summary]}`.

## `scidatamas_inspect_dataset`

`dataset_id`, `sample_rows` (по умолчанию 5, максимум 50). Возвращает summary, полную схему, `schema_text`, table-метаданные, sample rows, последнюю валидацию и последние 20 событий.

## `scidatamas_add_data`

| Аргумент | Тип | Смысл |
|---|---|---|
| `dataset_id` | string | да |
| `paths` | string[] | файлы/каталоги для file-датасета |
| `metadata` | json | объект на все, массив по файлам, mapping file→values; для table — массив row-записей с `id` |
| `notes` | string | уточнение пользователя: фиксация, объектив, единицы, что в файле |
| `dry_run` | boolean | только stage |
| `commit` | boolean | авто-коммит готового stage (по умолчанию true) |
| `activate` | boolean | активировать после коммита (по умолчанию true) |
| `author` | string | автор записей |
| `metadata_overrides` | json | значения на этапе коммита |

Возвращает либо `{committed:false, stage, ready, message}`, либо `{committed:true, stage, committed_count, files, dataset}`.

Правила:

- обязательные поля не выдумываются: stage с `missing` не коммитится автоматически;
- одна невалидная запись отменяет весь коммит;
- для table-датасета `metadata` — это аннотации существующих строк, а не новая таблица;
- каждый stage/commit пишется в `events.jsonl`.

## `scidatamas_commit_add`

`dataset_id`, `stage_id`, `metadata_overrides` (json), `notes`, `activate`. Повторно валидирует строго и либо коммитит всё, либо отказывает с перечнем недостающих полей.

## `scidatamas_get_data`

| Аргумент | Тип | Смысл |
|---|---|---|
| `query` | string | что нужно найти |
| `dataset_id` | string | явный датасет (иначе выбор моделью/лексикой) |
| `limit` | integer | 1–200, по умолчанию 50 |
| `include_files` | boolean | резолвить пути (по умолчанию true) |
| `include_preview` | boolean | текстовые выдержки/размеры изображений |
| `fields` | string[] | проекция |

Возвращает `dataset`, `selection`, `plan` (фильтр, поля, reasoning, fallback), `matched`, `returned`, `rows`, `files`, `hints`.

Фильтр — JSON DSL; SQL не исполняется. Если планировщик недоступен, работает лексический поиск.

## `scidatamas_import_external`

| Аргумент | Тип | Смысл |
|---|---|---|
| `url` | string | Zenodo record/API/DOI или прямой HTTP(S) файл |
| `mode` | `analyze` \| `import` | по умолчанию analyze |
| `dataset_name` | string | имя нового датасета; по умолчанию title записи |
| `dataset_id` | string | добавить в существующий датасет |
| `description`, `purpose` | string | переопределения |
| `rich` | boolean | DAG-схема |
| `include`, `exclude` | string[] | glob-паттерны |
| `max_files` | integer | по умолчанию 100 |
| `author`, `modality` | string | |
| `activate` | boolean | по умолчанию true |

`analyze` возвращает `source`, `files`, `total_bytes`, `record` без скачивания. `import` дополнительно создаёт/выбирает датасет, скачивает, инспектирует, маппит DOI/license/creators/publication_date, stage+commit, пишет `external_imported`.

Ограничения: приватные хосты блокируются, если `allowPrivateHosts=false`; суммарный размер ограничен `maxDownloadBytes`; при ошибке staging сохраняется в `_imports/<id>`.

## `scidatamas_status`

Без аргументов. Возвращает root, storage driver, число датасетов, доступность модели (provider/model), лимиты. Удобно для диагностики перед долгим workflow.

## Типовые ошибки

| Код | Причина |
|---|---|
| `SCIDATAMAS_NO_MODEL` | нет выбранной модели и не задан provider/model |
| `SCIDATAMAS_NO_LLM` | в профиле не смонтирован `ctx.llm` |
| `SCIDATAMAS_BAD_JSON` | модель не вернула валидный JSON после ретраев |
| `SCIDATAMAS_MISSING_FIELDS` | commit без обязательных полей |
| `SCIDATAMAS_SCHEMA_REMOVAL` | update удаляет поля без `allow_removals` |
| `SCIDATAMAS_NOT_FOUND` | нет датасета |
| `SCIDATAMAS_NO_STAGE` | нет stage с таким id |
| `SCIDATAMAS_FILE_TOO_LARGE` | превышен `maxFileBytes`/`maxDownloadBytes` |
| `SCIDATAMAS_PRIVATE_HOST` | импорт с localhost/private IP без разрешения |
| `SCIDATAMAS_BAD_DAG` | DAG не прошёл валидатор после ремонта |
| `SCIDATAMAS_TABLE_REQUIRED` | `layout=table` без `table_path` |

## Web API панели

Маршрут регистрируется только в Web-профиле: `/scidatamas/api`. Доступ проверяется через `connection.admit(req)` и разрешён только owner-peer.

| Метод | Путь | Ответ |
|---|---|---|
| GET | `/scidatamas/api/status` | `{status}`: root, storage, datasets, model, limits |
| GET | `/scidatamas/api/datasets?query=&include_drafts=` | `{root, storage, datasets[]}` |
| GET | `/scidatamas/api/datasets/<id>` | `{dataset, schema, schema_text, table, sample_rows, validation, events}` |
| GET | `/scidatamas/api/datasets/<id>/content?limit=&offset=` | постраничные строки метаданных и порядок колонок (вкладка Content) |
| GET | `/scidatamas/api/datasets/<id>/content?format=csv` | те же строки в виде скачиваемого CSV |
| GET | `/scidatamas/api/datasets/<id>/validation` | `{validation}` — полный latest-отчёт |
| GET | `/scidatamas/api/datasets/<id>/file?path=files/...` | байты артефакта |

Ограничения API:

- только `GET`/`HEAD`;
- файл отдаётся только из `datasets/<id>/files/...`;
- `..` и абсолютные ключи запрещены;
- remote-бэкенд вернёт 501 до появления materialization-кэша;
- запись через API отсутствует: изменения идут через инструменты агента.
