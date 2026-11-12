# Provenance of this snapshot

This directory is a source snapshot of the **SciDataMAS plugin for DeepSeek
Harness**, included in the umbrella repository so that one clone or one QR code
gives access to both the research code and the runnable plugin. Until the
standalone repository is public, this directory is the public source of truth
for the plugin; after the release, the standalone repository becomes the
upstream source of truth.

- Snapshot date: **2026-11-11**
- Base upstream commit: **e63f833** (`Fixed plagun UI + fixed error with llm including`)
- Upstream development repository: <https://github.com/AS2/scidatamas_dsh>
  (access may be restricted until the public release)
- The snapshot also contains the authors' working-tree fixes present on the
  snapshot date (UI, Web API, docs and tests).

The plugin is self-contained plain ESM; no build step is required. Its own
`LICENSE`, `CITATION.cff`, `CHANGELOG.md` and `package.json` are preserved.

When the standalone repository becomes public, it should be treated as the
upstream source of truth; this copy can then be updated or replaced by a git
submodule without changing the umbrella layout.
