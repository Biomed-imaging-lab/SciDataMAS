# Glossary / Глоссарий / 术语表

A short shared vocabulary for the plugin, the papers, and the user-testing notes.

| English | Русский | 中文 | Meaning |
|---|---|---|---|
| dataset | датасет | 数据集 | A named collection of artifacts, a schema, metadata rows, and audit history. |
| data lake | озеро данных | 数据湖 | The root collection of datasets plus catalog, logs, staging, and import areas. |
| schema | схема | 模式 | Fields that describe one element of a dataset, with types, units, and requirements. |
| metadata row | строка метаданных | 元数据行 | One record describing a file, an artifact, or a table row. |
| reserved field | системное поле | 保留字段 | Organizational field added by the lake: `id`, `author`, `uploaded_at`, `file_path`, `source_url`. |
| provenance | происхождение | 溯源 | Where an object came from: physical sample, capture, or computation. |
| DAG | DAG / граф | 有向无环图 | Directed acyclic graph of experimental steps: entity → signal → derivative. |
| entity | сущность | 实体 | A physical object or sample. |
| signal | сигнал | 信号 | Digital data captured from an entity. |
| derivative | производные данные | 派生数据 | Digital data computed from signals or other derivatives. |
| single-call | single-call / один вызов | 单次调用 | One model call that produces a compact schema. |
| rich / DAG mode | rich / DAG-режим | 富模式 / DAG 模式 | Per-node generation that produces a larger schema. |
| staging | staging / стейджинг | 暂存 | A proposed add that is not yet copied into the lake. |
| commit | коммит | 提交 | Strict validation plus copying files and writing metadata. |
| debate validation | дебатная валидация | 辩论式验证 | Simulated peer review that measures which schema fields answer real questions. |
| coverage | покрытие | 覆盖率 | Share of user fields actually used by reviewers. |
| clarification | уточнение | 待澄清问题 | A question the researcher should answer to close a metadata gap. |
| retrieval | поиск / извлечение | 检索 | Natural-language query turned into a safe JSON filter. |
| sidecar | sidecar / сайдкар | 附属元数据 | Metadata stored next to a table but keyed by row, without duplicating the table. |
| row key | ключ строки | 行键 | The table column that identifies a row and links it to sidecar metadata. |
| artifact | артефакт | 产物 / 文件 | A stored file or table that belongs to a dataset. |
| owner peer | owner-peer | 所有者对等端 | The authenticated DSH client allowed to read the Web panel API. |
