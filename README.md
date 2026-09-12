# GP2 transfer plan apps

Two Streamlit prototypes that replace the GP2 Site Interest Form and turn its
answers into a concrete data/sample transfer plan.

| Stage | App | When it is filled | What it produces |
|---|---|---|---|
| 1 | `sif_stage1_app.py` | A cohort first expresses interest, before any agreement | What exists, at domain level, with rough numbers — enough to decide genotyping vs sequencing |
| 2 | `transfer_plan_stage2_app.py` | The DTA/MTA is being drawn up | Which GP2 data dictionary instruments, for which phenotypes, how many participants, by when |

Stage 1 exports JSON; Stage 2 reads it and pre-selects instruments. Neither
stores anything — closing the browser loses the work. That is the main thing
standing between this and production.

```bash
pip install -r requirements.txt
streamlit run sif_stage1_app.py           # or transfer_plan_stage2_app.py
```

Click **Load an example cohort** in the sidebar to see either app populated.

---

## Files

| Path | What it is |
|---|---|
| `sif_stage1_app.py` | Stage 1. Six screens. |
| `transfer_plan_stage2_app.py` | Stage 2. Seven screens. Contains `INSTRUMENT_GROUPS`, the only hand-maintained mapping in the project. |
| `report.py` | PDF generation, shared by both apps. |
| `check_vocab.py` | Compares the vocabulary against the GP2 Data Dictionary. Read-only. |
| `vocab/*.csv` | The vocabulary. Edit these rather than the code — [`vocab/README.md`](vocab/README.md) documents every column. |
| `tests/test_smoke.py` | `pytest -q`. Run before and after every change. |
| `docs/DESIGN.md` | Why the model looks like this. Read once before changing anything structural. |
| `CLAUDE.md` | Context for Claude Code / Copilot, including the Streamlit traps. |
---

## Changing things

**Most changes are CSV edits, not code.** Adding a clinical domain, changing
which ones start ticked, rewording the examples a PI sees — all of that lives in
`vocab/gp2_L1_constructs.csv`. Adding a biosample is one line in
`vocab/gp2_biosamples.csv`. **[`vocab/README.md`](vocab/README.md) documents
every file and column, and is the first thing to read before editing them.**

**`INSTRUMENT_GROUPS` in `transfer_plan_stage2_app.py` is the exception.** It
maps what a cohort sees ("MDS-UPDRS") to the dictionary modalities that carry it
(`MDS-UPDRS Part I` … `Part IV`), and sets which options start ticked. It is in
the code because it encodes clinical judgement, not data. It is the one place to
edit for instrument-level changes.

**After any dictionary release, run the checker:**

```bash
python check_vocab.py                       # fetches the dictionary from GitHub
python check_vocab.py --dd local_copy.csv   # or use a local file
```

It reports new, removed, renamed and moved modalities and items, and exits
non-zero if something needs a human. It never edits the vocabulary — roughly a
third of the item tags are review decisions a diff cannot reproduce.

**Three rules worth knowing before you touch the screens:**

1. Never feed a widget's own output back in as its `value=`, `default=`, or as
   the frame handed to `st.data_editor`.
2. Anything the user decided must be re-seeded from the plain-dict store when a
   screen is revisited, never from its default.
3. Don't cache the vocabulary CSVs. They exist to be edited.

All three have caused real bugs. `CLAUDE.md` explains why.

---

## Where this is going

The prototype is not finished. The immediate work is tuning parameters —
which domains start ticked, which instruments are the default for each, the
wording a PI reads — against feedback from GP2 collaborators. Nothing
structural should be needed for that; it is mostly CSV editing and short
sessions with the people who will send the form out.

Once that settles, production needs:

- **Persistence.** A cohort gets a unique GP2 study code at the end of Stage 1.
  Stage 2 then loads by that code rather than by uploading a JSON file. Firestore
  is the obvious fit — the app is a UI over a table, and the hand-off is a record
  lookup.
- **Authentication.** Per-cohort tokenised links. Cohort PIs will not create
  accounts, and Stage 1 in particular is a first contact where friction costs
  submissions.
- **Deployment.** Streamlit Community Cloud is fine for review. Cloud Run
  (`gp2-data-explorer`) is the production path; note that Streamlit keeps session
  state in memory, so it must run pinned to a single instance until the state
  lives in a database.

None of this is worth starting before the prototype is signed off.
