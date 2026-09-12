# Working on this repo

Two Streamlit apps. Stage 1 collects what a cohort has; Stage 2 turns it into a
transfer plan. `docs/DESIGN.md` explains the model. This file is about working
on the code without reintroducing bugs that have already been fixed.

**Run `pytest -q` before and after every change.** Streamlit's failure mode is a
silently wrong value, not a crash, so the tests assert specific behaviours that
have broken before rather than aiming for coverage.

---

## The Streamlit traps

Every one of these has cost a debugging round. They look like the app ignoring
the user, not like an error.

### 1. Never feed a widget's output back in as its own input

```python
# BROKEN — editor's output becomes its input next rerun
st.session_state["grid"] = st.data_editor(build_grid(...), key="ed")

# BROKEN — multiselect's output becomes its default next rerun
scope["items"] = st.multiselect("...", ALL, default=scope["items"])
```

Streamlit keeps a widget's pending change as a diff against the object or
default it was handed. Hand it something new next rerun and the widget is
treated as new, so the change is discarded — every value has to be entered
twice, and multiselects cannot be built up one item at a time.

The pattern used instead:

- **Widgets own their value via `key`.** No `value=`, `default=`, `index=`
  computed from state the app also writes.
- `sync_from_widgets()` derives the plain dicts once per run, in `main()`.
- Grids get a cached frame from `editor_source()` that is the *same object*
  every rerun; the editor's return value goes to a different session key.

### 2. Widget state does not survive navigation

Streamlit discards the `session_state` entry for any keyed widget that was not
rendered on the previous run. It survives one rerun, then goes.

- **Plain widgets** (`w_*`): `persist_widget_state()` re-assigns each key at the
  top of `main()`. Add any new widget key to `WIDGET_KEYS` or it will silently
  reset.
- **Data editors**: their state *cannot* be re-assigned — Streamlit does not
  allow setting `st.session_state` for `st.data_editor`. Instead `_nav` (bumped
  in `main()` when the step changes) is folded into every editor signature, so
  returning to a screen rebuilds the frame from the stored output.
- **Anything the user decided** (`inst::`, `seg::`, `on::`) must be re-seeded
  **from the store, not from its default**, or unticking a default-on option
  undoes itself the moment the user navigates away. Seed from defaults on the
  first visit only — see `_inst_init`.

### 3. Do not cache the vocabulary

`@st.cache_data` on the CSV loader means an edit does nothing until the server
restarts, which looks exactly like the feature being broken. The files are a few
hundred rows; re-read them every run. `load_vocab()` also checks for required
columns and says so on screen if an old copy is in place.

### 4. Bare expressions get rendered

Streamlit's "magic" turns any bare expression statement into `st.write`,
including inside functions. `sel.add(m) if cond else sel.discard(m)` returns
`None` and paints a grey `None` box on the page. Use statements.

### 5. Widget keys must be unique per run

One instrument can serve several domains. Rendering a checkbox for it under each
one raises `StreamlitDuplicateElementKey`. Screen 2 de-duplicates by listing
every instrument once with all its domains in one column.

### 6. Choosing a control

`SelectboxColumn` costs two clicks to change a value — wrong for the most
repeated action in the app. Two checkboxes are one click each but can express a
contradiction (unticked "collected" with ticked "LT"). `st.segmented_control` is
one click, sets the value directly, and cannot represent a meaningless state.

- Binary question inside a table → `CheckboxColumn`
- Three-state question → `st.segmented_control` outside the table
- Seed its key from the store when absent, never via `default=`

### 7. reportlab units and XML

In `report.py`, `frame(widths=...)` takes **relative weights**, not units.
Bare numbers passed to reportlab are points, so a column meant to be 40 mm comes
out 14 mm and wraps one character per line. All user text goes through `esc()` —
reportlab parses Paragraph text as XML, so `H&Y < 3` silently becomes `H&Y;`.
Free-text criteria fields contain exactly that.

---

## Invariants

Changes that violate these are wrong even if they look like improvements.

1. **The unit is participants, counted once per item.** One person giving blood,
   plasma and DNA is +1 in each of those three rows. Never aliquots or visits.
2. **DNA sets the denominator** — or, when the cohort has no extracted DNA, the
   material GP2 would extract from. See `dna_basis()`. Coverage is always
   derived, never asked.
3. **Both stages are filled once.** Stage 1 at first contact, Stage 2 at
   contracting. Nobody is asked to come back and re-report, so there is no
   "previously reported" column anywhere. If one reappears, the model has been
   misunderstood.
4. **Cross-sectional vs longitudinal belongs to the (item, phenotype) pair.** A
   cohort can follow MMSE longitudinally in PD and take it once in controls.
5. **L1 and L2 are never mapped to each other directly.** See `docs/DESIGN.md`.
6. **Stage 1 suggests, it never decides.** The mapping is many-to-many, so Stage
   1 answers cannot determine Stage 2 rows. Forward: pre-selection. Backward:
   the reconciliation table on the review screen.
7. **Store long, present wide.** One row per `phenotype × item × period`. Adding
   an instrument, a phenotype or a year never changes the schema.
8. **Nothing blocks on a Stage 1/Stage 2 disagreement.** Stage 1 is an estimate
   made months earlier, often by someone else. The value is that the change is
   visible, not that it is prevented.

---

## Where to change what

| To change | Edit |
|---|---|
| Clinical domains, their defaults, their example text | `vocab/gp2_L1_constructs.csv` |
| Which domains start ticked in Stage 1 | `default_on` column, same file |
| Domains that cannot be longitudinal | `fixed_design` column, same file |
| Biosamples, omics | `vocab/gp2_biosamples.csv`, `vocab/gp2_omics.csv` |
| Which instruments Stage 2 offers, their labels, defaults, notes | `INSTRUMENT_GROUPS` in `transfer_plan_stage2_app.py` |
| Disease-specific scale scoping | `SCALE_PHENOTYPES`, same file |
| Domains dropped from Stage 2 | `NOT_OFFERED_IN_STAGE2`, same file |
| Modalities the app names ahead of the dictionary | `vocab/pending_modalities.txt` |
| PDF layout | `report.py` |

`vocab/gp2_L2_to_L1.csv` and `vocab/gp2_L3_item_tags.csv` are generated from the
data dictionary plus human review. Edit them when the dictionary changes, guided
by `check_vocab.py` — not by hand-editing to make a symptom go away.

### Adding a column to a count grid

Three places, in order: `make_grid` (the column), `grid_config` (its type and
help), `melt_grid` (recognising it, via `numeric_cols` if it is a count).
Missing the third is the usual bug — the column shows in the UI but never
reaches the export.

---

## Known rough edges

- **No persistence.** Stage 1 → JSON file → Stage 2 by hand. See README.
- `Mortality` is named in `INSTRUMENT_GROUPS` ahead of the data dictionary and
  listed in `pending_modalities.txt`. Remove that line once the dictionary
  splits it out of `PD History`.
- Screen 3 of both apps renders one control per row × phenotype. Fine at the
  sizes tested; a cohort selecting everything across many phenotypes will feel
  it. No pagination.
- `n_followup` counts *participants contributing a repeat*, not observations.
  Visits per person is not captured beyond the free-text interval.
- `CBD-Armstrong` and `CBS-Armstrong` both exist in the dictionary and are
  treated as one option. `PSP-RS` exists alongside `PSP-RS part I`–`VI`.
- CT, MRI and PET are asked at Stage 1 but have no dictionary schema, so they
  cannot be planned at Stage 2. They carry a ⚠︎ and appear in
  `NOT_OFFERED_IN_STAGE2`.

---

## Style

Plain Streamlit — no custom CSS, no component libraries. `st.data_editor` grids
rather than stacks of individual inputs: faster to fill and they match the long
storage format row for row. Keep it that way; the point of the prototype is the
interaction design, not the styling.
