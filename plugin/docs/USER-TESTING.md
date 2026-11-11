# SciDataMAS user-testing protocol

**English** · [Русский](USER-TESTING.ru.md) · [中文](USER-TESTING.zh.md)

This document is for the facilitator. It is written so that a 45–60 minute session produces comparable notes across participants and a clear list of fixes.

The goal is **not** to prove that the plugin works. It is to learn:

1. whether researchers understand what the lake is for;
2. where the create → validate → add → retrieve flow breaks down;
3. whether the generated metadata feels scientifically credible;
4. which panel information is actually used;
5. what people would need before trusting the lake with real data.

## 1. Session setup

### Facilitator checklist

- [ ] DSH Web profile starts and the **Data** panel is visible.
- [ ] A test lake root exists outside the repository, e.g. `~/data/scidatamas-ut-<participant>`.
- [ ] At least one sample folder with 3–10 realistic files is available (images, CSV, or both).
- [ ] A small public Zenodo record is chosen for the import task (or skip task 6).
- [ ] The model route works (`scidatamas_status` says the model is available).
- [ ] Screen recording and note-taking are ready, with consent.
- [ ] The participant has signed/recorded consent for anonymized notes.

### What to tell the participant

> We are testing a research prototype that helps organize scientific data and generate metadata. It is not a finished product. There are no wrong answers; we are testing the tool, not you. Please think aloud, and stop whenever something feels unclear. Do not use confidential or unpublished data in this session.

Disclose the current limitations:

- the panel is read-only;
- S3/Synology storage is not implemented;
- table append is not implemented;
- the model can be slow or return malformed JSON;
- generated metadata can be wrong and must be reviewed.

## 2. Roles

| Role | Responsibility |
|---|---|
| Facilitator | Reads tasks, asks neutral follow-ups, keeps time. Does not explain the interface unless the participant is blocked for more than 3 minutes. |
| Participant | Thinks aloud, performs tasks in their own words. |
| Observer (optional) | Records quotes, hesitations, errors, and timestamps; does not intervene. |

## 3. Agenda (60 minutes)

| Time | Segment |
|---|---|
| 0–5 | Welcome, consent, context |
| 5–10 | Warm-up questions about current data practice |
| 10–20 | Task 1: create a dataset |
| 20–30 | Task 2: validate and refine the schema |
| 30–42 | Task 3: add data and handle a missing field |
| 42–50 | Task 4: retrieve data; Task 5: inspect the panel |
| 50–55 | Task 6 (optional): external import or table dataset |
| 55–60 | Feedback form and wrap-up |

If the participant is slower, drop task 6 and keep the feedback.

## 4. Warm-up (5 minutes)

Ask, without showing the plugin:

1. Where do you currently keep the data from one experiment?
2. How do you record preparation and acquisition parameters?
3. What would a colleague need to reuse this dataset six months from now?
4. What usually goes missing?
5. Have you ever tried to reuse someone else’s dataset? What stopped you?

Record exact phrases. These become the evaluation vocabulary for the rest of the session.

## 5. Tasks

For each task record: start time, end time, completed (yes/partially/no), number of facilitator interventions, and quotes.

### Task 1 — Create a dataset (10 minutes)

Prompt:

> Create a dataset for the files in `<sample folder>`. Describe what one file/row represents and what you want to reuse the data for. Use the compact schema first.

Observe:

- does the participant understand the difference between a dataset and a folder?
- do they provide a purpose unprompted?
- do they read the generated schema?
- do they notice the reserved fields (`id`, `author`, `uploaded_at`, `file_path`, `source_url`)?
- do they ask for rich/DAG mode, and why?

Follow-ups:

- “Which fields would you remove?”
- “Which field is missing for your own reuse?”
- “What does `draft` mean to you?”

### Task 2 — Validate and refine (10 minutes)

Prompt:

> Run a debate validation on this dataset. Look at the report and decide what to change.

Observe:

- do they understand coverage and “useful fields”?
- do they read unanswered questions and clarifications?
- do they add fields, rewrite descriptions, or ignore the report?
- do they notice that the schema is not changed automatically?
- do they activate the dataset too early?

Follow-ups:

- “Which clarification is most useful? Which one is noise?”
- “Would you trust this coverage number? Why?”
- “What would make the debate feel like a real reviewer?”

### Task 3 — Add data and handle a gap (12 minutes)

Prompt:

> Add `<second sample subset>` to the dataset. Ask the assistant to show the staged metadata before committing. One required field is missing; decide what to do.

Observe:

- do they review the stage before committing?
- do they understand that no files are copied yet?
- how do they supply the missing value (text, metadata override, or by editing the schema)?
- do they notice the audit trail?
- do they check the active status after commit?

Follow-ups:

- “What would you expect if one file is wrong?”
- “Would you prefer to edit the stage in the panel? Why?”
- “What would make you comfortable committing without reviewing every row?”

### Task 4 — Retrieve (8 minutes)

Prompt:

> Find a subset of the data using a scientific condition, not a file name. Show the file paths.

Observe:

- do they phrase the query semantically?
- do they check which dataset was selected?
- do they understand the filter/plan explanation?
- do they trust the returned rows?
- what do they do when the result is empty?

Follow-ups:

- “What would you do differently with 10,000 rows?”
- “What should the answer include besides paths?”

### Task 5 — Inspect the panel (5 minutes)

Prompt:

> Open the Data panel and find the schema, validation, samples, and events for this dataset.

Observe:

- do they find the sidebar entry?
- which tab do they open first?
- do they understand scope/required/unit columns?
- do they use Copy id / Refresh?
- what is missing for a quick sanity check?

### Task 6 — Optional: external import or table (5 minutes)

Prompt A (import):

> Analyze a small Zenodo record and import only one type of file.

Prompt B (table):

> Create a table dataset from this CSV and describe the columns.

Observe only if time permits.

## 6. Feedback form

Use a 1–5 scale (1 = strongly disagree, 5 = strongly agree), then open questions.

### Perceived usefulness

1. The tool solves a problem I actually have.
2. The generated schema looked scientifically plausible.
3. The debate report helped me improve the schema.
4. The staged add made me more confident in the data.
5. I would use this for a real dataset after some fixes.
6. I would recommend it to a colleague.

### Ease of use

7. I understood what to do without help.
8. The panel information was easy to find.
9. The agent’s explanations were clear.
10. Error messages told me what to do next.

### Open questions

1. What was the most useful moment in the session?
2. What was the most confusing moment?
3. Which field or question was clearly wrong?
4. What would you need before trusting the lake with real data?
5. If you could change one thing first, what would it be?
6. Would you use this with images, tables, spectroscopy, sequencing, or something else?

### Single ease question (SEQ)

> Overall, how easy or difficult was it to accomplish the tasks today? (1 = very difficult, 7 = very easy)

## 7. Observation sheet

| Time | Task | Event / quote | Severity (1–3) | Notes |
|---|---|---|---|---|
| | | | | |

Severity: 1 = cosmetic, 2 = slowed the task, 3 = blocked the task or produced a wrong result.

## 8. Success criteria

A session is “successful” if the participant can, without facilitator intervention:

- create a draft with a plausible schema;
- read and act on at least one clarification;
- stage an add and explain why a missing field blocks the commit;
- retrieve a semantically described subset;
- find schema/validation/samples in the panel.

Track time-to-first-dataset and time-to-first-commit. These are more informative than a single satisfaction score.

## 9. Privacy and data handling

- Use only sample or public data.
- Do not record API keys, credentials, or personal data.
- Anonymize participant ids (`P1`, `P2`, …).
- Store recordings and notes in the agreed location; delete raw recordings after the agreed period.
- If the participant says something sensitive, stop the recording or mark the timestamp for redaction.

## 10. Known limitations to disclose

- Panel is read-only.
- No S3/Synology backend yet.
- No new-row append for table datasets.
- No Parquet/Excel/HDF5 inspection.
- Model generation can be slow, expensive, or wrong.
- One lake is intended for one DSH process at a time.
- Imported artifacts are copied; the lake is not a backup system.

## 11. Bug-report template

```text
Title:
Environment: DSH version, model, OS, lake root
Task:
What I did:
What I expected:
What happened:
Reproduction steps:
Tool output / screenshot:
Severity: cosmetic / slows the task / blocks the task / wrong result
Would I trust the result? yes / no / after fixes
```

## 12. After the session

Within 24 hours:

1. Clean the notes and remove sensitive content.
2. Convert quotes into findings, not feature requests.
3. Tag each finding: comprehension, workflow, metadata quality, panel, performance, trust.
4. Rank by severity and frequency.
5. Add the top three to the next iteration; do not try to fix everything.

A useful summary has one page: what worked, what blocked, what to change next, and the exact quotes that justify each change.
