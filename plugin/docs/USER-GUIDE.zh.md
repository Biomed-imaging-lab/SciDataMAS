# SciDataMAS 用户指南

[English](USER-GUIDE.md) · [Русский](USER-GUIDE.ru.md) · **中文**

本指南面向将使用 DSH 插件的研究人员和演示主持人，而不是插件开发者。内容涵盖安装、第一个数据集、各项主要工作流，以及通常容易出错的地方。

- [1. 工具简介](#1-what-this-tool-is)
- [2. 开始之前](#2-before-you-start)
- [3. 安装与配置](#3-install-and-configure)
- [4. 数据面板](#4-the-data-panel)
- [5. 创建数据集](#5-create-a-dataset)
- [6. 验证模式](#6-validate-a-schema)
- [7. 完善并启用](#7-refine-and-activate)
- [8. 添加数据](#8-add-data)
- [9. 检索数据](#9-retrieve-data)
- [10. 从 Zenodo 或 URL 导入](#10-import-from-zenodo-or-a-url)
- [11. 表格数据集](#11-tabular-datasets)
- [12. 数据的存放位置](#12-where-the-data-lives)
- [13. 故障排查](#13-troubleshooting)
- [14. 常见问题](#14-faq)

<a id="1-what-this-tool-is"></a>

## 1. 工具简介

SciDataMAS 是一个 DSH 插件，它在你的机器上维护一个**科学数据湖**。一个数据湖包含多个数据集。每个数据集包括：

- 名称、描述、用途、状态和来源；
- 元数据模式（字段包含类型、描述、单位，以及是否为必填）；
- 元数据行，每个文件或每个表行对应一行；
- 数据文件本身；
- 审计日志，以及可选的验证报告。

你通过聊天中的智能体进行操作，并在**数据**面板中查看数据湖。智能体使用工具；在当前版本中，面板是只读的。

<a id="2-before-you-start"></a>

## 2. 开始之前

你需要：

- 一个可用的 DSH 配置（面板默认使用 `web`）；
- 在 DSH 中配置好的模型路由（插件使用会话模型）；
- 一个用于数据湖的目录，且有足够的磁盘空间；
- 用于真实测试的示例文件（几张图片、一个 CSV 文件，或一个小文件夹）。

插件不存储 API 密钥。模型调用通过 `ctx.llm` 进行，因此 DSH 其他部分所用的提供方设置同样适用。

推荐的测试根目录：

```text
/home/<you>/data/scidatamas
```

不要将根目录指向 `/`、你的主目录，或包含无关文件的目录。插件会在其下创建 `datasets/`、`logs/`、`staging/` 和 `_imports/`。

<a id="3-install-and-configure"></a>

## 3. 安装与配置

### 方式 A：插件管理器

```bash
dsh plugin --profile web add file:$PWD
```

`pnpm` 必须可用。该 bundle 会自动启用。

### 方式 B：手动符号链接（无需构建步骤）

```bash
mkdir -p "$DSH_HOME/profiles/web/node_modules"
ln -sfn "$PWD" \
  "$DSH_HOME/profiles/web/node_modules/scidatamas-dsh-plugin"
```

在 `$DSH_HOME/profiles/web/cordis.patch.yml` 中添加：

```yaml
- insert:
    - id: scidatamas
      name: scidatamas-dsh-plugin
      config:
        root: /home/alex/data/scidatamas
        author: Your Name
```

### Linux 上找不到 `dsh`

DSH 可能从 npx 缓存或桌面应用启动，因此 PATH 中可能没有 `dsh` 命令——apt 里的 `dsh` 包与本项目无关。先找到真正的 CLI：

```bash
find "$HOME/.npm/_npx" -path '*/node_modules/.bin/dsh' -print
```

用绝对路径调用，或设置别名：

```bash
alias dsh="$(find "$HOME/.npm/_npx" -path '*/node_modules/.bin/dsh' -print -quit)"
dsh --version
```

通过插件管理器安装还需要 `pnpm`。如果没有 `pnpm`，请使用符号链接安装脚本，它会安全地修改配置补丁并创建数据湖根目录：

```bash
./scripts/install-local.sh
```

如果配置不是 `~/.dsh/profiles/web`，请先设置 `DSH_HOME` 和 `DSH_PROFILE`。

重启 Web 配置（或让 HMR 应用该补丁）。向智能体询问：

> 显示 `scidatamas_status`。

你应该能看到根目录、存储驱动、数据集数量、模型可用性和各项限制。

### 配置参考

| 字段 | 默认值 | 说明 |
|---|---|---|
| `root` | `.scidatamas` | 数据湖目录，可为绝对路径，或相对于进程工作目录的路径。 |
| `author` | 空 | 记录在元数据行中的默认作者。 |
| `provider`, `model` | 空 | 可选的模型路由覆盖。为空表示“使用会话模型”。 |
| `maxSchemaFields` | `200` | 生成字段的硬性上限。 |
| `maxDagNodes` | `24` | DAG 节点的硬性上限。 |
| `dagConcurrency` | `3` | 每个节点的并行生成调用数。 |
| `debateRuns` | `3` | 默认的辩论轮数。 |
| `debateRoles` | `4` | 每轮的评审角色数。 |
| `debateQuestionsPerRole` | `4` | 每轮每个角色的问题数。 |
| `maxFileBytes` | `512 MiB` | 复制到数据湖中的最大文件。 |
| `maxDownloadBytes` | `2 GiB` | 外部导入的总大小上限。 |
| `maxFilesPerAdd` | `200` | 每次添加/导入调用的文件数。 |
| `maxRowsScan` | `200000` | 从表中扫描的行数。 |
| `allowNetwork` | `true` | 启用外部导入。 |
| `allowPrivateHosts` | `false` | 允许从 localhost/私有 IP 导入。 |
| `storageDriver` | `local` | `local`、`s3`、`synology`（后两者为扩展点）。 |
| `logLlmCalls` | `true` | 将提示/响应写入 `logs/llm-calls.jsonl`。 |

<a id="4-the-data-panel"></a>

## 4. 数据面板

侧边栏中的**数据**入口会打开一个面板，包含：

- 可搜索的数据集列表；
- 数据集指标（记录数、文件数、模式版本、布局）；
- **模式** — 字段名、类型、作用域、必填/可选、单位、描述；
- **验证** — 覆盖率、有用/未使用字段、未回答问题、待澄清问题、建议字段；
- **样本** — 元数据行和指向数据文件的链接；
- **事件** — 创建、暂存、提交、验证、检索、导入；
- **刷新**和**复制 ID**。

要在查看数据时保留对话，请点击面板顶部的**在聊天旁打开**（或从右侧边栏的添加菜单中选择 Data）。面板会停靠到右侧，主区域回到对话。

面板通过 `/scidatamas/api` 读取数据，并且仅对与 Web GUI 其余部分相同的属主对等端可用。如果面板显示**模型不可用**，存储仍然可用；只有生成和验证不可用。

<a id="5-create-a-dataset"></a>

## 5. 创建数据集

用自然语言提问即可。智能体会选择工具。一个好的请求应包含：

- 名称；
- 一行/一个元素代表什么；
- 数据的产生方式；
- 预期的复用方式；
- 示例路径（如果存在）。

示例：

> 从 `/data/exp1` 创建一个数据集 `confocal_cells_2026`。描述：PFA 固定的 HeLa 细胞的共聚焦 z 轴层扫，40×，每个视野一个层扫。用途：复用于细胞分割。使用紧凑模式并向我展示字段。

工具会检查示例并返回带有模式的草稿。数据集默认处于**草稿**状态。

对于多步骤实验，可要求丰富的元数据：

> 该实验包含样本制备、共聚焦采集和 Cellpose 分割。请使用丰富的 DAG 工作流创建数据集。

`scidatamas_create_dataset_dag` 会生成更多字段，并附加 `node_id`/`node_description`；字段数量可能超出任何一次复用所需。

<a id="6-validate-a-schema"></a>

## 6. 验证模式

> 对 `confocal_cells_2026` 运行三轮辩论式验证，并展示模式无法回答的问题。

报告包含：

- **覆盖率** — 回答了评审问题的用户字段所占比例；
- **有用字段** — 每个字段被使用的次数，以及出现在多少轮中；
- **未使用字段** — 可删除或需要更好描述的候选字段；
- **未回答问题** — 缺口集合；
- **待澄清问题** — 面向研究人员的具体问题；
- **建议字段** — 建议新增的字段及其名称/类型。

模式不会被修改。请根据待澄清问题决定要添加什么。

<a id="7-refine-and-activate"></a>

## 7. 完善并启用

> 添加 `pixel_size_nm`、`objective` 和 `fixation`；用“PFA-fixed, permeabilized”改进描述；将状态设为 active。

`scidatamas_update_dataset` 会递增 `schema_version`，清除 `validated_schema_version`，并记录此次更改。删除字段需要 `allow_removals=true`。

只有在模式经过审查后，才应启用数据集。面板会显示 `draft`、`active` 或 `archived`。

<a id="8-add-data"></a>

## 8. 添加数据

### 先审阅

> 将 `/data/exp2` 添加到 `confocal_cells_2026`。暂时不要提交。注意：4% PFA，物镜 40×/1.3 oil，像素尺寸 100 nm。

带 `dry_run=true` 或 `commit=false` 的 `scidatamas_add_data` 会返回一个**暂存**：每个文件的建议元数据、缺失的必填字段和警告。不会复制任何内容。

### 提交

> 用这些值提交暂存。

`scidatamas_commit_add` 会对每条记录进行严格的重新验证。如果仍有必填字段缺失，提交会被拒绝，且不会复制任何文件。

### 显式值

你可以传入应用于所有文件的值对象、与文件对齐的数组，或 `file → values` 映射。用户给出的值优先于模型填充的值。

### 如果智能体无法标注某个字段

这是正常情况。用文本回答：

> 缺失的 `fixation` 值是“4% PFA for 15 min at RT”；`z_slices` 是 31。

然后用 `metadata_overrides` 提交；审计日志会保留该澄清。

<a id="9-retrieve-data"></a>

## 9. 检索数据

> 查找所有像素尺寸小于 150 nm、在三月之后创建的共聚焦层扫，并显示文件路径。

检索工作流会选择数据集、规划 JSON 过滤器、验证字段名，并返回行及解析后的路径。如果规划失败，会使用词法回退；响应会在 `plan.used_fallback` 中说明。

设置 `include_preview=true` 可获得简短文本摘录或图像尺寸。面板的样本选项卡会链接到数据文件本身。

<a id="10-import-from-zenodo-or-a-url"></a>

## 10. 从 Zenodo 或 URL 导入

先从分析开始：

> 分析 Zenodo 记录 5512749。有多少文件，什么格式，什么许可证？

然后带过滤器导入：

> 从该记录导入 `**/*.tif`，最多 20 个文件。根据记录元数据创建数据集并启用它。

过程如下：

1. 通过 Zenodo API 读取记录；
2. 将选中的文件下载到 `_imports/<id>/`；
3. 检查文件并生成模式；
4. 创建数据集（或使用已有的 `dataset_id`）；
5. 将 DOI/许可证/创建者/发布日期映射到模式；
6. 暂存并提交文件；
7. 成功后删除暂存，失败时保留以便检查。

直接使用 HTTP(S) 文件 URL 时走同一路径。除非设置 `allowPrivateHosts: true`，否则私有主机将被阻止。

<a id="11-tabular-datasets"></a>

## 11. 表格数据集

当主要数据文件是表格时，使用 `layout="table"`：

> 从 `/data/measurements.csv` 创建一个表格数据集；第一列是 `participant_id`。请描述每一列。

规则：

- 表格作为规范数据文件保留在 `files/` 中；
- 模式描述列（`scope: "column"`）以及可选的行级字段；
- `metadata.jsonl` 中为每个表行存储一行伴随元数据，以行键为键；
- `get_data` 会合并列和伴随元数据行；
- 行键依次从 `id`/`row_id`/`row`/`index`/`sample_id`/`key` 中选择，然后选第一个唯一列，最后使用行索引；
- 支持为已有行添加标注；暂不支持追加新行。

<a id="12-where-the-data-lives"></a>

## 12. 数据的存放位置

```text
<root>/
  catalog.json
  datasets/<id>/
    manifest.json
    metadata.jsonl
    metadata.csv
    files/...
    events.jsonl
    validation/latest.json
    validation/history.jsonl
    staging/<stage_id>.json
  logs/llm-calls.jsonl
  _imports/<import_id>/
```

`manifest.json` 是模式和数据集状态的权威来源。`metadata.jsonl` 是行存储。`metadata.csv` 是扁平导出。`events.jsonl` 是审计记录。启用 `logLlmCalls` 时，`logs/llm-calls.jsonl` 包含内部提示/响应。

请备份整个根目录；在会话正在写入时，不要手动编辑 `manifest.json`。

<a id="13-troubleshooting"></a>

## 13. 故障排查

| 现象 | 可能原因 | 处理方法 |
|---|---|---|
| `SCIDATAMAS_NO_MODEL` / “模型不可用” | 未选择会话模型，且未配置 provider/model | 在 DSH 中选择模型，或在插件配置中设置 `provider`/`model`。 |
| `SCIDATAMAS_NO_LLM` | 该配置没有 `ctx.llm` 服务 | 使用带后端的 Web 配置。仅存储类工具仍可使用。 |
| 面板显示“尚无数据集” | 数据湖为空，或长时间运行的服务器中的编目信息已过期 | 创建一个数据集，然后按刷新。 |
| `SCIDATAMAS_MISSING_FIELDS` | 提交时缺少必填字段 | 查看缺失列表；提供 `metadata_overrides` 或说明澄清内容。 |
| `SCIDATAMAS_FILE_TOO_LARGE` | 文件超过 `maxFileBytes` 或 `maxDownloadBytes` | 提高限制或缩小导入范围。 |
| `SCIDATAMAS_PRIVATE_HOST` | 从 localhost/私有 IP 导入 | 如果信任来源，设置 `allowPrivateHosts: true`。 |
| `SCIDATAMAS_BAD_JSON` | 模型在重试后仍未返回有效 JSON | 重试；若持续出现，改用更强的模型或降低字段上限。 |
| `SCIDATAMAS_NO_DATASET_MATCH` | 检索无法选择数据集 | 显式传入 `dataset_id`。 |
| `SCIDATAMAS_TABLE_REQUIRED` | 使用了 `layout="table"` 但没有 `table_path` | 提供 CSV/TSV/JSON/JSONL 路径。 |
| `SCIDATAMAS_SCHEMA_REMOVAL` | 更新会删除字段 | 如果确属有意，用 `allow_removals=true` 确认。 |

更多错误码见 [TOOLS.md](TOOLS.md)。

<a id="14-faq"></a>

## 14. 常见问题

**模型会看到我的原始文件吗？**  
不会。插件发送文件名、格式、大小、图像尺寸、表头、JSON 结构和简短的文本摘录。二进制内容不会发送给模型。

**我的 API 密钥在哪里？**  
不在插件中的任何地方。它使用 DSH LLM 服务和配置的凭据。

**我可以不使用 Web 面板吗？**  
可以。这些工具可在无头模式和其他配置中使用；客户端部分仅限 Web。

**多个人可以写入同一个数据湖吗？**  
目前还不安全。编目锁是进程内的。每个数据湖请使用一个 DSH 进程；跨进程锁定已在路线图中。

**我可以移动数据湖吗？**  
可以，前提是没有 DSH 进程正在写入。复制整个根目录并更新 `root`。Manifest 中的键是相对路径，因此副本可移植。

**现在支持 S3 或 Synology 吗？**  
不支持。存储接缝和桩代码已存在；真正的驱动是下一步开发工作。

**元数据模式是以 CSV 还是 JSON 存储？**  
模式位于 `manifest.json`；行位于 `metadata.jsonl`；`metadata.csv` 是便于使用的导出。
