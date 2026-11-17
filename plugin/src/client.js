window.__ModuleLoader__.load({
  id: 'scidatamas-dsh-plugin',
  factory: (require) => {
    var module = { exports: {} }
    var exports = module.exports
    Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' })

    const React = require('react')
    const { useState, useEffect, useCallback } = React
    const h = React.createElement
    const NS = 'scidatamas'
    const API = '/scidatamas/api'

    const CSS = `
.sdm-root{height:100%;display:flex;flex-direction:column;min-height:0;color-scheme:light dark;background:var(--dsw-alias-bg-base,Canvas);color:var(--dsw-alias-label-primary,CanvasText);font-size:13px;line-height:1.45}
.sdm-header{flex:none;display:flex;align-items:center;gap:12px;padding:14px 20px;border-bottom:1px solid var(--dsw-alias-border-l1,CanvasText);background:var(--dsw-alias-bg-base,Canvas)}
.sdm-title{font-size:15px;font-weight:600;letter-spacing:.01em;white-space:nowrap}
.sdm-sub{color:var(--dsw-alias-label-tertiary,GrayText);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sdm-spacer{flex:1;min-width:8px}
.sdm-chip{display:inline-flex;align-items:center;gap:5px;border:1px solid var(--dsw-alias-border-l2,ButtonBorder);border-radius:999px;padding:2px 9px;font-size:11px;color:var(--dsw-alias-label-secondary,ButtonText);background:var(--dsw-alias-bg-layer-2,ButtonFace);white-space:nowrap}
.sdm-chip-dot{width:6px;height:6px;border-radius:50%;background:var(--dsw-alias-state-success-primary,#2e9e5b)}
.sdm-chip-dot.warn{background:var(--dsw-alias-state-warn-primary,#c98a00)}
.sdm-chip-dot.err{background:var(--dsw-alias-state-error-primary,#c74444)}
.sdm-btn{border:1px solid var(--dsw-alias-border-l2,ButtonBorder);background:var(--dsw-alias-bg-layer-2,ButtonFace);color:var(--dsw-alias-label-primary,ButtonText);border-radius:7px;padding:5px 10px;font:inherit;font-size:12px;cursor:pointer;white-space:nowrap}
.sdm-btn:hover{background:var(--dsw-alias-interactive-bg-hover,ButtonFace)}
.sdm-btn:focus-visible{outline:2px solid var(--dsw-alias-state-business-primary,#4c7dff);outline-offset:1px}
.sdm-btn:disabled{opacity:.5;cursor:default}
.sdm-body{flex:1;display:grid;grid-template-columns:286px minmax(0,1fr);min-height:0}
.sdm-list{border-right:1px solid var(--dsw-alias-border-l1,CanvasText);display:flex;flex-direction:column;min-height:0;background:var(--dsw-alias-bg-layer-2,Canvas)}
.sdm-search{padding:10px;display:flex;gap:6px;flex:none}
.sdm-search input{flex:1;min-width:0;box-sizing:border-box;border:1px solid var(--dsw-alias-border-l2,ButtonBorder);border-radius:7px;background:var(--dsw-specific-input-major,Field);color:var(--dsw-alias-label-primary,FieldText);padding:6px 9px;font:inherit;font-size:12px}
.sdm-search input:focus{outline:2px solid var(--dsw-alias-state-business-primary,#4c7dff);outline-offset:-1px;border-color:transparent}
.sdm-items{flex:1;overflow:auto;padding:2px 8px 10px}
.sdm-item{display:block;width:100%;text-align:left;border:1px solid transparent;background:transparent;color:inherit;border-radius:8px;padding:8px 9px;margin:2px 0;cursor:pointer;font:inherit}
.sdm-item:hover{background:var(--dsw-alias-interactive-bg-hover,ButtonFace)}
.sdm-item.active{background:var(--dsw-alias-bg-layer-3,Highlight);border-color:var(--dsw-alias-border-l2,Highlight)}
.sdm-item-id{font-family:var(--ds-font-family-code,ui-monospace,monospace);font-size:11px;color:var(--dsw-alias-label-tertiary,GrayText);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sdm-item-name{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin:1px 0 2px}
.sdm-item-meta{display:flex;gap:6px;align-items:center;font-size:10.5px;color:var(--dsw-alias-label-tertiary,GrayText);white-space:nowrap;overflow:hidden}
.sdm-dot{width:6px;height:6px;border-radius:50%;background:var(--dsw-alias-state-idle-primary,GrayText);flex:none}
.sdm-dot.draft{background:var(--dsw-alias-state-warn-primary,#c98a00)}.sdm-dot.active{background:var(--dsw-alias-state-success-primary,#2e9e5b)}.sdm-dot.archived{background:var(--dsw-alias-state-idle-primary,GrayText)}
.sdm-detail{overflow:auto;min-width:0;padding:18px 22px 32px}
.sdm-detail-head{display:flex;align-items:flex-start;gap:10px;flex-wrap:wrap;margin-bottom:4px}
.sdm-detail-title{font-size:20px;font-weight:600;line-height:1.25;margin:0;min-width:0}
.sdm-detail-id{font-family:var(--ds-font-family-code,ui-monospace,monospace);font-size:12px;color:var(--dsw-alias-label-tertiary,GrayText);margin:2px 0 12px}
.sdm-desc{max-width:920px;color:var(--dsw-alias-label-secondary,CanvasText);white-space:pre-wrap;margin:8px 0}
.sdm-purpose{max-width:920px;color:var(--dsw-alias-label-tertiary,GrayText);margin:4px 0 12px}
.sdm-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin:14px 0 18px;max-width:920px}
.sdm-metric{border:1px solid var(--dsw-alias-border-l1,CanvasText);border-radius:8px;padding:8px 10px;background:var(--dsw-alias-bg-layer-2,Canvas)}
.sdm-metric-label{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--dsw-alias-label-tertiary,GrayText)}
.sdm-metric-value{font-size:15px;font-weight:600;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sdm-tabs{display:flex;gap:2px;border-bottom:1px solid var(--dsw-alias-border-l1,GrayText);margin:6px 0 14px;flex-wrap:wrap}
.sdm-tab{border:0;background:transparent;color:var(--dsw-alias-label-tertiary,GrayText);padding:7px 11px;border-bottom:2px solid transparent;cursor:pointer;font:inherit;font-size:12px}
.sdm-tab:hover{color:var(--dsw-alias-label-primary,CanvasText)}
.sdm-tab.active{color:var(--dsw-alias-label-primary,CanvasText);border-bottom-color:var(--dsw-alias-state-business-primary,#4c7dff);font-weight:500}
.sdm-section-title{font-size:13px;font-weight:600;margin:18px 0 8px}
.sdm-table-wrap{border:1px solid var(--dsw-alias-border-l1,GrayText);border-radius:8px;overflow:auto;max-width:100%}
.sdm-table{width:100%;border-collapse:collapse;font-size:12px;min-width:640px}
.sdm-table th{text-align:left;font-weight:600;font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;color:var(--dsw-alias-label-tertiary,GrayText);background:var(--dsw-alias-bg-layer-2,Canvas);padding:7px 9px;border-bottom:1px solid var(--dsw-alias-border-l1,CanvasText);position:sticky;top:0;z-index:1;white-space:nowrap}
.sdm-table td{padding:7px 9px;border-bottom:1px solid var(--dsw-alias-border-l1,GrayText);vertical-align:top}
.sdm-table tr:last-child td{border-bottom:0}
.sdm-table td.sdm-num{font-variant-numeric:tabular-nums;white-space:nowrap}
.sdm-field-name{font-family:var(--ds-font-family-code,ui-monospace,monospace);font-weight:500;white-space:nowrap}
.sdm-field-desc{color:var(--dsw-alias-label-secondary,CanvasText);min-width:260px}
.sdm-type{display:inline-block;border-radius:5px;background:var(--dsw-alias-bg-layer-3,ButtonFace);color:var(--dsw-alias-label-secondary,ButtonText);padding:0 5px;font-size:10.5px;font-family:var(--ds-font-family-code,ui-monospace,monospace)}
.sdm-req{color:var(--dsw-alias-state-error-primary,#c74444);font-size:10.5px}
.sdm-sys{opacity:.58}
.sdm-muted{color:var(--dsw-alias-label-tertiary,GrayText)}
.sdm-badge{display:inline-flex;align-items:center;gap:4px;border-radius:5px;padding:1px 6px;font-size:10.5px;background:var(--dsw-alias-bg-layer-3,ButtonFace);color:var(--dsw-alias-label-secondary,ButtonText)}
.sdm-badge.ok{background:color-mix(in srgb, var(--dsw-alias-state-success-primary,#2e9e5b) 14%, transparent);color:var(--dsw-alias-state-success-primary,#2e9e5b)}
.sdm-badge.warn{background:color-mix(in srgb, var(--dsw-alias-state-warn-primary,#c98a00) 15%, transparent);color:var(--dsw-alias-state-warn-primary,#a06d00)}
.sdm-badge.err{background:color-mix(in srgb, var(--dsw-alias-state-error-primary,#c74444) 13%, transparent);color:var(--dsw-alias-state-error-primary,#c74444)}
.sdm-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;min-height:280px;text-align:center;padding:28px;color:var(--dsw-alias-label-tertiary,GrayText)}
.sdm-empty-title{font-size:16px;font-weight:600;color:var(--dsw-alias-label-primary,CanvasText);margin-bottom:6px}
.sdm-empty-body{max-width:460px;line-height:1.55}
.sdm-empty code{font-family:var(--ds-font-family-code,ui-monospace,monospace);font-size:11px;background:var(--dsw-alias-bg-layer-2,Canvas);padding:1px 4px;border-radius:4px;color:var(--dsw-alias-label-secondary,CanvasText)}
.sdm-error{margin:12px 0;border:1px solid color-mix(in srgb, var(--dsw-alias-state-error-primary,#c74444) 35%, transparent);background:color-mix(in srgb, var(--dsw-alias-state-error-primary,#c74444) 7%, transparent);color:var(--dsw-alias-state-error-primary,#a33);border-radius:8px;padding:9px 11px;display:flex;gap:8px;align-items:center}
.sdm-link{color:var(--dsw-alias-state-business-primary,LinkText);text-decoration:none;font-family:var(--ds-font-family-code,ui-monospace,monospace);font-size:11.5px}
.sdm-link:hover{text-decoration:underline}
.sdm-list-section{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:4px 2px;color:var(--dsw-alias-label-tertiary,GrayText);font-size:10.5px;text-transform:uppercase;letter-spacing:.05em}
.sdm-field-list{margin:0;padding-left:18px}
.sdm-field-list li{margin:3px 0}
.sdm-code{font-family:var(--ds-font-family-code,ui-monospace,monospace);font-size:11.5px;white-space:pre-wrap;word-break:break-word}
.sdm-pre{margin:0;padding:10px 12px;border:1px solid var(--dsw-alias-border-l1,GrayText);border-radius:8px;background:var(--dsw-alias-bg-layer-2,Canvas);overflow:auto;max-height:360px;font-family:var(--ds-font-family-code,ui-monospace,monospace);font-size:11px;white-space:pre-wrap}
.sdm-bar{height:7px;border-radius:99px;background:var(--dsw-alias-bg-layer-3,ButtonFace);overflow:hidden;max-width:420px;margin:6px 0 2px}
.sdm-bar > span{display:block;height:100%;background:var(--dsw-alias-state-success-primary,#2e9e5b);border-radius:99px}
.sdm-inline{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.sdm-tag-list{display:flex;gap:5px;flex-wrap:wrap;margin:6px 0}
.sdm-root--pane .sdm-body{grid-template-columns:1fr;grid-template-rows:minmax(120px,34%) minmax(0,1fr)}
.sdm-root--pane .sdm-list{border-right:0;border-bottom:1px solid var(--dsw-alias-border-l1,CanvasText);max-height:none}
.sdm-root--pane .sdm-header{padding:10px 12px;gap:8px;flex-wrap:wrap}
.sdm-root--pane .sdm-title{font-size:13px}
.sdm-root--pane .sdm-sub{display:none}
.sdm-root--pane .sdm-detail{padding:12px 14px 24px}
.sdm-root--pane .sdm-metrics{grid-template-columns:repeat(auto-fit,minmax(96px,1fr))}
.sdm-root--pane .sdm-table{min-width:520px}
.sdm-content-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:0 0 8px}
.sdm-content-toolbar .sdm-btn{text-decoration:none;display:inline-flex;align-items:center}
.sdm-content-table td{font-family:var(--ds-font-family-code,ui-monospace,monospace);font-size:11px;white-space:pre-wrap;word-break:break-word;max-width:360px}
.sdm-content-table th{font-family:var(--ds-font-family-code,ui-monospace,monospace);text-transform:none;letter-spacing:0}
@media (max-width:820px){.sdm-body{grid-template-columns:1fr}.sdm-list{max-height:250px;border-right:0;border-bottom:1px solid var(--dsw-alias-border-l1,CanvasText)}.sdm-detail{padding:14px}}
`

    const messages = {
      en: {
        panel: 'Data',
        title: 'Scientific data',
        subtitle: 'SciDataMAS lake',
        search: 'Search datasets',
        refresh: 'Refresh',
        loading: 'Loading…',
        retry: 'Retry',
        datasets: 'datasets',
        noDatasets: 'No datasets yet',
        noDatasetsBody: 'Ask the agent in chat to create one. For example:',
        noDatasetsExample: 'Create a dataset with a compact metadata schema from /data/exp1 and show me the result.',
        selectDataset: 'Select a dataset',
        description: 'Description',
        purpose: 'Purpose',
        noDescription: 'No description.',
        noPurpose: 'No stated purpose.',
        status: 'Status',
        layout: 'Layout',
        records: 'Records',
        files: 'Files',
        schemaVersion: 'Schema',
        validated: 'Validated',
        notValidated: 'not validated',
        tableRows: 'Table rows',
        rowKey: 'Row key',
        tabsSchema: 'Schema',
        tabsValidation: 'Validation',
        tabsSamples: 'Samples',
        tabsContent: 'Content',
        tabsEvents: 'Events',
        contentHint: 'Metadata rows exactly as stored in metadata.csv.',
        downloadCsv: 'Download CSV',
        loadMore: 'Load more',
        noContent: 'No metadata rows',
        noContentBody: 'Add data or import a dataset to populate the metadata table.',
        field: 'Field',
        type: 'Type',
        required: 'Required',
        optional: 'Optional',
        scope: 'Scope',
        unit: 'Unit',
        details: 'Details',
        coverage: 'Coverage',
        usefulFields: 'Useful fields',
        unusedFields: 'Unused fields',
        unanswered: 'Unanswered questions',
        clarifications: 'Clarifications',
        suggestedFields: 'Suggested fields',
        noValidation: 'No validation report yet',
        noValidationBody: 'Run scidatamas_validate_schema to test the schema against simulated researchers.',
        noSamples: 'No rows yet',
        noSamplesBody: 'Add data with scidatamas_add_data or register a table.',
        noEvents: 'No events yet.',
        copyId: 'Copy id',
        copied: 'Copied',
        model: 'Model',
        modelUnavailable: 'model unavailable',
        openBesideChat: 'Open beside chat',
        storage: 'Storage',
        root: 'Root',
        openFile: 'open',
        table: 'Table',
        columns: 'columns',
        created: 'created',
        updated: 'updated',
        error: 'Request failed',
        schemaFields: 'fields',
        system: 'system',
        clarificationsHint: 'These questions are worth asking the researcher before activation.',
        samplesHint: 'Metadata rows and resolved file links.',
      },
      ru: {
        panel: 'Данные',
        title: 'Научные данные',
        subtitle: 'Озеро SciDataMAS',
        search: 'Поиск датасетов',
        refresh: 'Обновить',
        loading: 'Загрузка…',
        retry: 'Повторить',
        datasets: 'датасетов',
        noDatasets: 'Датасетов пока нет',
        noDatasetsBody: 'Попросите агента в чате создать датасет. Например:',
        noDatasetsExample: 'Создай датасет с компактной схемой метаданных по /data/exp1 и покажи результат.',
        selectDataset: 'Выберите датасет',
        description: 'Описание',
        purpose: 'Назначение',
        noDescription: 'Описание не задано.',
        noPurpose: 'Назначение не задано.',
        status: 'Статус',
        layout: 'Формат',
        records: 'Записей',
        files: 'Файлов',
        schemaVersion: 'Схема',
        validated: 'Валидирована',
        notValidated: 'не валидирована',
        tableRows: 'Строк таблицы',
        rowKey: 'Ключ строки',
        tabsSchema: 'Схема',
        tabsValidation: 'Валидация',
        tabsSamples: 'Примеры',
        tabsContent: 'Содержимое',
        tabsEvents: 'События',
        contentHint: 'Строки метаданных в том виде, в каком они сохранены в metadata.csv.',
        downloadCsv: 'Скачать CSV',
        loadMore: 'Показать ещё',
        noContent: 'Нет строк метаданных',
        noContentBody: 'Добавьте данные или импортируйте датасет, чтобы заполнить таблицу.',
        field: 'Поле',
        type: 'Тип',
        required: 'Обяз.',
        optional: 'Необяз.',
        scope: 'Уровень',
        unit: 'Ед.',
        details: 'Описание',
        coverage: 'Покрытие',
        usefulFields: 'Полезные поля',
        unusedFields: 'Неиспользованные поля',
        unanswered: 'Вопросы без ответа',
        clarifications: 'Уточнения',
        suggestedFields: 'Предложенные поля',
        noValidation: 'Отчёта валидации пока нет',
        noValidationBody: 'Запустите scidatamas_validate_schema, чтобы проверить схему на симулированных исследователях.',
        noSamples: 'Строк пока нет',
        noSamplesBody: 'Добавьте данные через scidatamas_add_data или зарегистрируйте таблицу.',
        noEvents: 'Событий пока нет.',
        copyId: 'Копировать id',
        copied: 'Скопировано',
        model: 'Модель',
        modelUnavailable: 'модель недоступна',
        openBesideChat: 'Открыть рядом с чатом',
        storage: 'Хранилище',
        root: 'Корень',
        openFile: 'открыть',
        table: 'Таблица',
        columns: 'колонок',
        created: 'создан',
        updated: 'обновлён',
        error: 'Ошибка запроса',
        schemaFields: 'полей',
        system: 'системное',
        clarificationsHint: 'Эти вопросы стоит задать исследователю до активации.',
        samplesHint: 'Строки метаданных и ссылки на файлы.',
      },
      zh: {
        panel: '数据',
        title: '科学数据',
        subtitle: 'SciDataMAS 数据湖',
        search: '搜索数据集',
        refresh: '刷新',
        loading: '加载中…',
        retry: '重试',
        datasets: '个数据集',
        noDatasets: '还没有数据集',
        noDatasetsBody: '在对话中让智能体创建一个。例如：',
        noDatasetsExample: '用 /data/exp1 创建一个带紧凑元数据模式的数据集，并展示结果。',
        selectDataset: '选择一个数据集',
        description: '描述',
        purpose: '用途',
        noDescription: '暂无描述。',
        noPurpose: '未说明用途。',
        status: '状态',
        layout: '布局',
        records: '记录',
        files: '文件',
        schemaVersion: '模式',
        validated: '已验证',
        notValidated: '未验证',
        tableRows: '表格行',
        rowKey: '行键',
        tabsSchema: '模式',
        tabsValidation: '验证',
        tabsSamples: '示例',
        tabsContent: '内容',
        tabsEvents: '事件',
        contentHint: '与 metadata.csv 中完全一致的元数据行。',
        downloadCsv: '下载 CSV',
        loadMore: '加载更多',
        noContent: '没有元数据行',
        noContentBody: '添加数据或导入数据集以填充元数据表。',
        field: '字段',
        type: '类型',
        required: '必填',
        optional: '可选',
        scope: '范围',
        unit: '单位',
        details: '详情',
        coverage: '覆盖率',
        usefulFields: '有用字段',
        unusedFields: '未使用字段',
        unanswered: '未回答的问题',
        clarifications: '待澄清',
        suggestedFields: '建议字段',
        noValidation: '还没有验证报告',
        noValidationBody: '运行 scidatamas_validate_schema，用模拟研究人员检验模式。',
        noSamples: '还没有行',
        noSamplesBody: '使用 scidatamas_add_data 添加数据，或注册表格。',
        noEvents: '还没有事件。',
        copyId: '复制 ID',
        copied: '已复制',
        model: '模型',
        modelUnavailable: '模型不可用',
        openBesideChat: '在聊天旁打开',
        storage: '存储',
        root: '根目录',
        openFile: '打开',
        table: '表格',
        columns: '列',
        created: '创建',
        updated: '更新',
        error: '请求失败',
        schemaFields: '个字段',
        system: '系统',
        clarificationsHint: '建议在激活前向研究人员确认这些问题。',
        samplesHint: '元数据行及解析后的文件链接。',
      },
    }

    function ensureCss() {
      if (typeof document === 'undefined') return
      const existing = document.querySelector('style[data-scidatamas-panel]')
      if (existing) return
      const tag = document.createElement('style')
      tag.dataset.scidatamasPanel = 'panel'
      tag.textContent = CSS
      document.head.appendChild(tag)
    }

    async function api(path) {
      const response = await fetch(`${API}${path}`, {
        credentials: 'same-origin',
        headers: { accept: 'application/json' },
      })
      const text = await response.text()
      let data
      try {
        data = text ? JSON.parse(text) : {}
      } catch {
        data = { error: text }
      }
      if (!response.ok) throw new Error(data?.error || `HTTP ${response.status}`)
      return data
    }

    function formatBytes(bytes) {
      if (typeof bytes !== 'number' || !Number.isFinite(bytes)) return '—'
      const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
      let value = bytes
      let index = 0
      while (value >= 1024 && index < units.length - 1) {
        value /= 1024
        index += 1
      }
      return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`
    }

    function formatValue(value) {
      if (value === undefined || value === null) return h('span', { className: 'sdm-muted' }, '—')
      if (typeof value === 'object') return h('span', { className: 'sdm-code' }, JSON.stringify(value))
      const text = String(value)
      return text.length > 220 ? h('span', { title: text }, `${text.slice(0, 220)}…`) : text
    }

    function fileHref(datasetId, path) {
      return `${API}/datasets/${encodeURIComponent(datasetId)}/file?path=${encodeURIComponent(path)}`
    }

    function StatusChip({ tone, children, title }) {
      return h('span', { className: 'sdm-chip', title }, h('span', { className: `sdm-chip-dot${tone ? ` ${tone}` : ''}` }), children)
    }

    function Metric({ label, value, title }) {
      return h('div', { className: 'sdm-metric', title },
        h('div', { className: 'sdm-metric-label' }, label),
        h('div', { className: 'sdm-metric-value' }, value))
    }

    function Empty({ title, body, example, t }) {
      return h('div', { className: 'sdm-empty' },
        h('div', { className: 'sdm-empty-title' }, title),
        h('div', { className: 'sdm-empty-body' }, body, example ? h('div', { style: { marginTop: 10 } }, h('code', null, example)) : null))
    }

    function SchemaTab({ detail, t }) {
      const fields = detail.schema?.fields ?? []
      return h('div', null,
        h('div', { className: 'sdm-inline', style: { marginBottom: 8 } },
          h('span', { className: 'sdm-muted' }, `${fields.length} ${t('schemaFields')}`),
          h('span', { className: 'sdm-muted' }, `v${detail.dataset.schema_version}`)),
        h('div', { className: 'sdm-table-wrap' },
          h('table', { className: 'sdm-table' },
            h('thead', null, h('tr', null,
              h('th', null, t('field')),
              h('th', null, t('type')),
              h('th', null, t('scope')),
              h('th', null, t('required')),
              h('th', null, t('unit')),
              h('th', null, t('details')))),
            h('tbody', null, fields.map((field) => h('tr', { key: field.name, className: field.system ? 'sdm-sys' : '' },
              h('td', null, h('span', { className: 'sdm-field-name' }, field.name)),
              h('td', null, h('span', { className: 'sdm-type' }, field.type)),
              h('td', null, h('span', { className: 'sdm-badge' }, field.scope === 'column' ? 'column' : field.system ? t('system') : 'row')),
              h('td', null, field.required ? h('span', { className: 'sdm-req' }, t('required')) : h('span', { className: 'sdm-muted' }, t('optional'))),
              h('td', null, field.unit || '—'),
              h('td', { className: 'sdm-field-desc' }, field.description || '—')))))),
        detail.schema?.warnings?.length ? h('div', { className: 'sdm-section-title' }, 'Warnings') : null,
        detail.schema?.warnings?.length ? h('ul', { className: 'sdm-field-list' }, detail.schema.warnings.map((warning, index) => h('li', { key: index }, warning))) : null)
    }

    function ValidationTab({ detail, t }) {
      const validation = detail.validation
      if (!validation) {
        return h(Empty, { title: t('noValidation'), body: t('noValidationBody'), t })
      }
      const coverage = Math.max(0, Math.min(1, Number(validation.coverage) || 0))
      return h('div', null,
        h('div', { className: 'sdm-inline' },
          h('span', { className: 'sdm-muted' }, `${t('coverage')}: ${(coverage * 100).toFixed(1)}%`),
          h('span', { className: 'sdm-muted' }, `schema v${validation.schema_version}`),
          h('span', { className: 'sdm-muted' }, `${validation.runs ?? 0} runs`)),
        h('div', { className: 'sdm-bar' }, h('span', { style: { width: `${coverage * 100}%` } })),
        h('div', { className: 'sdm-section-title' }, `${t('usefulFields')} (${validation.useful_fields ?? 0})`),
        validation.useful_fields_detail?.length
          ? h('div', { className: 'sdm-table-wrap' }, h('table', { className: 'sdm-table' },
            h('thead', null, h('tr', null, h('th', null, t('field')), h('th', null, 'Uses'), h('th', null, 'Runs'))),
            h('tbody', null, validation.useful_fields_detail.map((field) => h('tr', { key: field.name },
              h('td', null, h('span', { className: 'sdm-field-name' }, field.name)),
              h('td', { className: 'sdm-num' }, field.uses ?? '—'),
              h('td', { className: 'sdm-num' }, field.runs_used ?? '—'))))))
          : null,
        validation.unused_fields_detail?.length
          ? h('div', { className: 'sdm-section-title' }, `${t('unusedFields')} (${validation.unused_fields ?? 0})`)
          : null,
        validation.unused_fields_detail?.length
          ? h('div', { className: 'sdm-tag-list' }, validation.unused_fields_detail.map((name) => h('span', { key: name, className: 'sdm-badge' }, name)))
          : null,
        validation.unanswered_questions_detail?.length
          ? h('div', { className: 'sdm-section-title' }, `${t('unanswered')} (${validation.unanswered_questions ?? 0})`)
          : null,
        validation.unanswered_questions_detail?.length
          ? h('ul', { className: 'sdm-field-list' }, validation.unanswered_questions_detail.map((item, index) => h('li', { key: index }, item.text, item.count ? h('span', { className: 'sdm-muted' }, ` · ${item.count}×`) : null)))
          : null,
        validation.clarifications?.length
          ? h('div', null,
            h('div', { className: 'sdm-section-title' }, `${t('clarifications')} (${validation.clarifications.length})`),
            h('div', { className: 'sdm-muted', style: { marginBottom: 6 } }, t('clarificationsHint')),
            h('div', { className: 'sdm-table-wrap' }, h('table', { className: 'sdm-table' },
              h('thead', null, h('tr', null, h('th', null, '#'), h('th', null, t('clarifications')), h('th', null, t('suggestedFields')))),
              h('tbody', null, validation.clarifications.map((item, index) => h('tr', { key: index },
                h('td', { className: 'sdm-num' }, index + 1),
                h('td', null, item.question, item.why ? h('div', { className: 'sdm-muted', style: { fontSize: 11 } }, item.why) : null),
                h('td', null, item.suggested_field ? h('span', { className: 'sdm-field-name' }, item.suggested_field.name) : '—')))))))
          : h('div', { className: 'sdm-muted' }, `${t('unanswered')}: ${validation.unanswered_questions ?? 0}`),
        validation.report_path ? h('div', { className: 'sdm-muted', style: { marginTop: 10, fontSize: 11 } }, validation.report_path) : null)
    }

    function SamplesTab({ detail, t }) {
      const rows = detail.sample_rows ?? []
      const dataset = detail.dataset
      if (rows.length === 0) return h(Empty, { title: t('noSamples'), body: t('noSamplesBody'), t })
      const columns = []
      const seen = new Set()
      for (const row of rows) {
        for (const key of Object.keys(row)) {
          if (!seen.has(key)) { seen.add(key); columns.push(key) }
        }
      }
      const ordered = ['id', ...columns.filter((key) => key !== 'id')]
      return h('div', null,
        h('div', { className: 'sdm-muted', style: { marginBottom: 7 } }, t('samplesHint')),
        h('div', { className: 'sdm-table-wrap' }, h('table', { className: 'sdm-table' },
          h('thead', null, h('tr', null, ordered.map((key) => h('th', { key }, key)))),
          h('tbody', null, rows.map((row, index) => h('tr', { key: row.id ?? index },
            ordered.map((key) => h('td', { key, className: key === 'id' ? 'sdm-num' : '' },
              key === 'file_path' && row[key]
                ? h('a', { className: 'sdm-link', href: fileHref(dataset.id, row[key]), target: '_blank', rel: 'noreferrer' }, String(row[key]).split('/').pop())
                : formatValue(row[key])))))))))
    }

    function ContentTab({ content, loading, error, datasetId, onLoadMore, t }) {
      if (error) return h('div', { className: 'sdm-error' }, `${t('error')}: ${error}`)
      if (!content && loading) return h('div', { className: 'sdm-muted' }, t('loading'))
      if (!content) return h(Empty, { title: t('noContent'), body: t('noContentBody'), t })
      if (content.rows.length === 0) return h(Empty, { title: t('noContent'), body: t('noContentBody'), t })
      const columns = content.columns ?? []
      return h('div', null,
        h('div', { className: 'sdm-content-toolbar' },
          h('span', { className: 'sdm-muted' }, t('contentHint')),
          h('div', { className: 'sdm-spacer' }),
          h('span', { className: 'sdm-muted' }, `${content.rows.length} / ${content.total}`),
          h('a', {
            className: 'sdm-btn',
            href: `${API}/datasets/${encodeURIComponent(datasetId)}/content?format=csv`,
            download: `${datasetId}-metadata.csv`,
          }, t('downloadCsv')),
          content.has_more ? h('button', { className: 'sdm-btn', type: 'button', onClick: onLoadMore, disabled: loading }, loading ? t('loading') : t('loadMore')) : null),
        h('div', { className: 'sdm-table-wrap' }, h('table', { className: 'sdm-table sdm-content-table' },
          h('thead', null, h('tr', null, columns.map((key) => h('th', { key }, key)))),
          h('tbody', null, content.rows.map((row, index) => h('tr', { key: row.id ?? index },
            columns.map((key) => h('td', { key, className: key === 'id' ? 'sdm-num' : '' },
              key === 'file_path' && row[key]
                ? h('a', { className: 'sdm-link', href: fileHref(datasetId, row[key]), target: '_blank', rel: 'noreferrer' }, String(row[key]).split('/').pop())
                : formatValue(row[key])))))))))
    }

    function EventsTab({ detail, t }) {
      const events = detail.events ?? []
      if (events.length === 0) return h(Empty, { title: t('noEvents'), body: t('noEvents'), t })
      return h('div', { className: 'sdm-table-wrap' }, h('table', { className: 'sdm-table' },
        h('thead', null, h('tr', null, h('th', null, 'When'), h('th', null, 'Event'), h('th', null, 'Details'))),
        h('tbody', null, [...events].reverse().map((event, index) => h('tr', { key: index },
          h('td', { className: 'sdm-num sdm-muted' }, event.ts ? new Date(event.ts).toLocaleString() : '—'),
          h('td', null, h('span', { className: 'sdm-badge' }, event.type ?? 'event')),
          h('td', { className: 'sdm-code' }, formatValue(Object.fromEntries(Object.entries(event).filter(([key]) => !['ts', 'type'].includes(key))))))))))
    }

    function DatasetDetail({ detail, tab, setTab, t, content, contentLoading, contentError, onContentMore }) {
      const dataset = detail.dataset
      const validation = detail.validation
      const tabs = [
        ['schema', `${t('tabsSchema')} ${detail.schema?.fields?.length ?? 0}`],
        ['validation', t('tabsValidation')],
        ['samples', t('tabsSamples')],
        ['content', `${t('tabsContent')} ${content?.total ?? detail.dataset.counts?.records ?? 0}`],
        ['events', t('tabsEvents')],
      ]
      return h('div', null,
        h('div', { className: 'sdm-detail-head' },
          h('h2', { className: 'sdm-detail-title' }, dataset.name),
          h(StatusChip, { tone: dataset.status === 'active' ? '' : dataset.status === 'draft' ? 'warn' : 'err' }, dataset.status),
          h('span', { className: 'sdm-chip' }, dataset.layout),
          validation ? h('span', { className: 'sdm-badge ok' }, `${t('validated')} v${validation.schema_version}`) : h('span', { className: 'sdm-badge warn' }, t('notValidated'))),
        h('div', { className: 'sdm-detail-id' }, dataset.id),
        h('div', { className: 'sdm-desc' }, dataset.description || t('noDescription')),
        dataset.purpose ? h('div', { className: 'sdm-purpose' }, `${t('purpose')}: ${dataset.purpose}`) : null,
        h('div', { className: 'sdm-metrics' },
          h(Metric, { label: t('records'), value: dataset.counts?.records ?? 0 }),
          h(Metric, { label: t('files'), value: dataset.counts?.files ?? 0 }),
          h(Metric, { label: t('schemaVersion'), value: `v${dataset.schema_version}` }),
          h(Metric, { label: t('layout'), value: dataset.layout }),
          dataset.table ? h(Metric, { label: t('tableRows'), value: dataset.table.row_count, title: `${t('rowKey')}: ${dataset.table.row_key}` }) : null),
        detail.table ? h('div', { className: 'sdm-muted', style: { marginBottom: 8 } },
          `${t('table')}: `, h('span', { className: 'sdm-code' }, detail.table.path),
          ` · ${detail.table.columns?.length ?? 0} ${t('columns')} · ${t('rowKey')}: `,
          h('span', { className: 'sdm-code' }, detail.table.row_key)) : null,
        h('div', { className: 'sdm-tabs' }, tabs.map(([id, label]) => h('button', {
          key: id,
          className: `sdm-tab${tab === id ? ' active' : ''}`,
          type: 'button',
          onClick: () => setTab(id),
        }, label))),
        tab === 'schema' ? h(SchemaTab, { detail, t }) : null,
        tab === 'validation' ? h(ValidationTab, { detail, t }) : null,
        tab === 'samples' ? h(SamplesTab, { detail, t }) : null,
        tab === 'content' ? h(ContentTab, { content, loading: contentLoading, error: contentError, datasetId: detail.dataset.id, onLoadMore: onContentMore, t }) : null,
        tab === 'events' ? h(EventsTab, { detail, t }) : null)
    }

    function SciDataPanel({ t, compact = false, onSplit }) {
      const [datasets, setDatasets] = useState([])
      const [status, setStatus] = useState(null)
      const [selected, setSelected] = useState(null)
      const [detail, setDetail] = useState(null)
      const [query, setQuery] = useState('')
      const [tab, setTab] = useState('schema')
      const [listLoading, setListLoading] = useState(true)
      const [detailLoading, setDetailLoading] = useState(false)
      const [error, setError] = useState('')
      const [refresh, setRefresh] = useState(0)
      const [copied, setCopied] = useState(false)
      const [content, setContent] = useState(null)
      const [contentLoading, setContentLoading] = useState(false)
      const [contentError, setContentError] = useState('')

      const split = () => {
        if (!onSplit) return
        const result = onSplit()
        if (result && result.ok === false) setError(result.error || 'Unable to open the panel beside chat')
      }

      const loadList = useCallback(async (search) => {
        setListLoading(true)
        setError('')
        try {
          const [list, statusResult] = await Promise.all([
            api(`/datasets?query=${encodeURIComponent(search ?? '')}`),
            api('/status'),
          ])
          const next = list.datasets ?? []
          setDatasets(next)
          setStatus(statusResult.status ?? null)
          setSelected((previous) => (previous && next.some((dataset) => dataset.id === previous) ? previous : next[0]?.id ?? null))
        } catch (failure) {
          setError(failure.message)
        } finally {
          setListLoading(false)
        }
      }, [])

      useEffect(() => {
        const timer = setTimeout(() => { loadList(query) }, 250)
        return () => clearTimeout(timer)
      }, [query, loadList, refresh])

      useEffect(() => {
        if (!selected) { setDetail(null); return }
        let active = true
        setDetailLoading(true)
        setError('')
        api(`/datasets/${encodeURIComponent(selected)}`)
          .then((result) => { if (active) setDetail(result) })
          .catch((failure) => { if (active) setError(failure.message) })
          .finally(() => { if (active) setDetailLoading(false) })
        return () => { active = false }
      }, [selected, refresh])

      useEffect(() => {
        if (tab !== 'content' || !selected) return
        let active = true
        setContent(null)
        setContentLoading(true)
        setContentError('')
        api(`/datasets/${encodeURIComponent(selected)}/content?limit=200&offset=0`)
          .then((result) => { if (active) setContent(result) })
          .catch((failure) => { if (active) setContentError(failure.message) })
          .finally(() => { if (active) setContentLoading(false) })
        return () => { active = false }
      }, [selected, tab, refresh])

      const loadMoreContent = () => {
        if (!content || !selected) return
        const nextOffset = (content.offset ?? 0) + content.rows.length
        setContentLoading(true)
        setContentError('')
        api(`/datasets/${encodeURIComponent(selected)}/content?limit=200&offset=${nextOffset}`)
          .then((result) => setContent((previous) => previous
            ? { ...result, offset: previous.offset, rows: [...previous.rows, ...result.rows] }
            : result))
          .catch((failure) => setContentError(failure.message))
          .finally(() => setContentLoading(false))
      }

      const copyId = () => {
        if (!detail?.dataset?.id || !navigator.clipboard) return
        navigator.clipboard.writeText(detail.dataset.id).then(() => {
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        }).catch(() => {})
      }

      const model = status?.model
      return h('div', { className: `sdm-root${compact ? ' sdm-root--pane' : ''}` },
        h('header', { className: 'sdm-header' },
          h('div', null,
            h('div', { className: 'sdm-title' }, t('title')),
            h('div', { className: 'sdm-sub' }, `${t('subtitle')} · ${status?.root ?? '…'} · ${t('storage')}: ${status?.storage ?? '…'}`)),
          h('div', { className: 'sdm-spacer' }),
          h(StatusChip, { tone: model?.available ? '' : 'warn', title: model?.error ?? '' }, model?.available ? `${model.provider}/${model.model}` : t('modelUnavailable')),
          h(StatusChip, null, `${datasets.length} ${t('datasets')}`),
          !compact && onSplit ? h('button', { className: 'sdm-btn', type: 'button', onClick: split, title: t('openBesideChat') }, t('openBesideChat')) : null,
          h('button', { className: 'sdm-btn', type: 'button', onClick: () => { setRefresh((value) => value + 1) }, disabled: listLoading }, t('refresh'))),
        h('div', { className: 'sdm-body' },
          h('aside', { className: 'sdm-list' },
            h('div', { className: 'sdm-search' },
              h('input', {
                value: query,
                placeholder: t('search'),
                'aria-label': t('search'),
                onChange: (event) => setQuery(event.target.value),
              })),
            h('div', { className: 'sdm-list-section' },
              h('span', null, listLoading ? t('loading') : `${datasets.length} ${t('datasets')}`)),
            h('div', { className: 'sdm-items' },
              datasets.map((dataset) => h('button', {
                key: dataset.id,
                type: 'button',
                className: `sdm-item${selected === dataset.id ? ' active' : ''}`,
                onClick: () => { setSelected(dataset.id); setTab('schema') },
              },
                h('div', { className: 'sdm-item-id' }, dataset.id),
                h('div', { className: 'sdm-item-name' }, dataset.name),
                h('div', { className: 'sdm-item-meta' },
                  h('span', { className: `sdm-dot ${dataset.status}` }),
                  h('span', null, dataset.status),
                  h('span', null, '·'),
                  h('span', null, dataset.layout),
                  h('span', null, '·'),
                  h('span', null, `${dataset.counts?.records ?? 0} rec`))))),
            datasets.length === 0 && !listLoading
              ? h('div', { style: { padding: '12px 8px' } },
                h('div', { className: 'sdm-muted' }, t('noDatasets')),
                h('div', { className: 'sdm-muted', style: { fontSize: 11, marginTop: 4 } }, t('noDatasetsBody')),
                h('code', { className: 'sdm-code', style: { display: 'block', marginTop: 8, fontSize: 10.5 } }, t('noDatasetsExample')))
              : null),
          h('main', { className: 'sdm-detail' },
            error ? h('div', { className: 'sdm-error' },
              h('span', null, `${t('error')}: ${error}`),
              h('button', { className: 'sdm-btn', type: 'button', onClick: () => setRefresh((value) => value + 1) }, t('retry'))) : null,
            !selected
              ? h(Empty, {
                title: datasets.length === 0 ? t('noDatasets') : t('selectDataset'),
                body: t('noDatasetsBody'),
                example: t('noDatasetsExample'),
                t,
              })
              : detailLoading && !detail
                ? h('div', { className: 'sdm-muted' }, t('loading'))
                : detail
                  ? h('div', null,
                    h('div', { className: 'sdm-inline', style: { marginBottom: 4 } },
                      h('button', { className: 'sdm-btn', type: 'button', onClick: copyId }, copied ? t('copied') : t('copyId'))),
                    h(DatasetDetail, { detail, tab, setTab, t, content, contentLoading, contentError, onContentMore: loadMoreContent }))
                  : null)))
    }

    function DataIcon() {
      return h('svg', { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', 'aria-hidden': 'true' },
        h('ellipse', { cx: 12, cy: 5.5, rx: 7.5, ry: 3, stroke: 'currentColor', strokeWidth: 1.5 }),
        h('path', { d: 'M4.5 5.5v6c0 1.66 3.36 3 7.5 3s7.5-1.34 7.5-3v-6', stroke: 'currentColor', strokeWidth: 1.5 }),
        h('path', { d: 'M4.5 11.5v6c0 1.66 3.36 3 7.5 3s7.5-1.34 7.5-3v-6', stroke: 'currentColor', strokeWidth: 1.5 }))
    }

    const inject = ['slots', 'locale', 'layout', 'sidebarRight', 'sidebarRightTabs']

    function apply(ctx) {
      ensureCss()
      ctx.effect(() => ctx.locale.register(NS, messages), 'scidatamas: panel dictionaries')
      const bound = ctx.locale.bind(NS)
      const t = (key) => {
        const value = bound(key)
        return value === key ? (messages.en[key] ?? key) : value
      }
      const openBesideChat = () => {
        try {
          ctx.layout.selectPanel(null)
          ctx.sidebarRight.openTab('scidatamas-data')
          return { ok: true }
        } catch (error) {
          return { ok: false, error: error?.message ?? String(error) }
        }
      }
      const Page = (props) => h(SciDataPanel, { ...props, t, onSplit: openBesideChat })
      const Pane = (props) => h(SciDataPanel, { ...props, t, compact: true })
      ctx.effect(() => ctx.sidebarRightTabs.register({
        id: 'scidatamas-dsh-plugin/data',
        kind: 'scidatamas-data',
        title: () => t('panel'),
        guide: [{
          id: 'data',
          order: 30,
          title: () => t('panel'),
          description: () => t('subtitle'),
          icon: DataIcon,
        }],
      }), 'scidatamas: right sidebar type')
      ctx.slots.inject('sidebar.right.pane.tab', () => ctx.slots.register({
        name: 'sidebar.right.pane.tab',
        key: 'scidatamas-dsh-plugin/data',
        locale: NS,
      }, Pane))
      ctx.slots.inject('main', () => ctx.slots.register({
        name: 'main',
        key: 'scidatamas',
        locale: NS,
      }, Page))
      ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({
        name: 'sidebar.panellist',
        id: 'scidatamas',
        order: 20,
        locale: NS,
        label: () => t('panel'),
      }, DataIcon))
    }

    exports.NS = NS
    exports.messages = messages
    exports.CSS = CSS
    exports.apply = apply
    exports.inject = inject
    return module.exports
  },
})
