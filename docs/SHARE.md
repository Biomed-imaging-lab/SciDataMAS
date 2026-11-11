# Share kit

Everything needed to put the repository on a slide, a poster or a social post.

## Links

| Purpose | URL |
|---|---|
| Repository (star / fork) | <https://github.com/Biomed-imaging-lab/SciDataMAS> |
| Plugin directory | <https://github.com/Biomed-imaging-lab/SciDataMAS/tree/main/plugin> |
| Star | <https://github.com/Biomed-imaging-lab/SciDataMAS/stargazers> |
| Fork | <https://github.com/Biomed-imaging-lab/SciDataMAS/fork> |
| Citation metadata | <https://github.com/Biomed-imaging-lab/SciDataMAS/blob/main/CITATION.cff> |

## QR files

| File | Points to | Use |
|---|---|---|
| `docs/assets/qr-repo.png` | repository root | poster / slide / handout; people can star and share from there |
| `docs/assets/qr-repo.svg` | repository root | print at any size |
| `docs/assets/qr-plugin.png` | `main/plugin` | if you want to send people straight to the plugin |
| `docs/assets/qr-plugin.svg` | `main/plugin` | print at any size |

> The QR codes point at `main`. Merge the publication branch before printing,
> otherwise the plugin QR will open a 404 until the branch is merged.

Regenerate after a URL change:

```bash
python3 -m pip install "qrcode[pil]"
python3 scripts/make_qr.py
```

Practical tip: print the repo QR at **4–5 cm** on a poster and test it with two
different phones before the session.

## Ready-to-post text

### English

> **SciDataMAS — LLM-driven scientific data management, now with a DeepSeek
> Harness plugin.**
>
> The plugin turns a DSH session into a local-first scientific data lake:
> adaptive metadata schemas, debate-based schema validation, staged
> human-in-the-loop ingestion, natural-language retrieval, Zenodo import and a
> native Data panel. The same repository contains the research code, the
> curated data and the experiment harness behind the 2026 metadata-curation
> paper.
>
> ⭐ Star / fork: https://github.com/Biomed-imaging-lab/SciDataMAS
>
> #SciDataMAS #DeepSeekHarness #ScientificData #Metadata #LLM #AI4Science

### Русский

> **SciDataMAS — LLM-мультиагентная система для научных данных, теперь с
> плагином для DeepSeek Harness.**
>
> Плагин превращает сессию DSH в локальное научное хранилище: адаптивные схемы
> метаданных, проверка схемы имитацией рецензирования, поэтапное добавление
> данных с обязательными полями, поиск на естественном языке, импорт из Zenodo
> и нативная панель Data. В том же репозитории — код статьи, выверенные данные
> и экспериментальный стенд.
>
> ⭐ Поставить звезду / форкнуть: https://github.com/Biomed-imaging-lab/SciDataMAS
>
> #SciDataMAS #DeepSeekHarness #научныеданные #метаданные #LLM

## One-line pitch

> SciDataMAS makes a metadata schema a first-class object: generate it, debate
> it, validate it, and only then let data into the lake.

## Share buttons

- X: <https://twitter.com/intent/tweet?text=SciDataMAS%20%E2%80%94%20LLM-driven%20scientific%20data%20management%20with%20a%20DeepSeek%20Harness%20plugin&url=https://github.com/Biomed-imaging-lab/SciDataMAS>
- LinkedIn: <https://www.linkedin.com/sharing/share-offsite/?url=https://github.com/Biomed-imaging-lab/SciDataMAS>
- Telegram: <https://t.me/share/url?url=https://github.com/Biomed-imaging-lab/SciDataMAS&text=SciDataMAS%20%E2%80%94%20LLM-driven%20scientific%20data%20management>
