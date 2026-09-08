# GP2 transfer plan app — handover notes

Everything in one file: `transfer_plan_app.py` (~880 lines). No database, no auth. Prototype for discussion.

```
pip install -r requirements.txt
streamlit run transfer_plan_app.py
```

Click **Load an example cohort** in the sidebar to see it populated.

This file doubles as the instruction file for Claude Code. Read it before changing anything.

---

## What the app does

Cohort PIs lay out their whole transfer plan **once**, at contracting — how many participants, per phenotype, per material, per clinical domain. A completed study gives one set of numbers; an ongoing study projects year by year until collection ends. GP2 compares the plan against what arrives and nudges the cohorts that lag badly.

Full requirements live in `transfer_plan_input_spec.md`. This file is only about the code.

---

## Six rules that must not be broken

Changes that violate these are wrong even if they look like improvements.

1. **The unit is participants, counted once per item.** One person giving blood + plasma + DNA is +1 in each of those three rows. Never aliquots, tubes, or visits.
2. **DNA is the denominator.** DNA counts per phenotype define cohort size. Coverage is always derived from them, never asked as a question. This is why DNA has its own screen and comes first.
3. **This is filled once, not annually.** PIs project forward; they are never asked to come back and re-report. Nothing shows them what they said last time, and there is no "previously reported" column. If someone reintroduces one, the model has been misunderstood.
4. **Cross-sectional vs longitudinal belongs to the (item, phenotype) pair, not to the study or the item alone.** This holds for biosamples as much as clinical domains — `kind` is `"sample"` or `"clinical"` and the machinery is shared. A ten-year cohort still collects family history once, and it can follow MMSE longitudinally in PD while taking it once in controls. `design_of(domain, phenotype)` is the single source of truth; it returns `None` when that arm does not collect the domain at all.
5. **Store long, present wide.** One row per `phenotype × item × period`, where `period` is `baseline` or a year. Never widen the schema to add a domain, a phenotype or a year. Wide tables are pivots at display time.
6. **Ask what exists, then ask numbers.** Scope screen first, grids filtered to what was selected. This is the entire reason the app exists rather than a form. A change that shows a PI items they did not select is a regression.

---

## Where to change what

| To change | Edit | Line ≈ |
|---|---|---|
| Phenotype list | `PHENOTYPES` | 24 |
| Biosample list (non-DNA) | `OTHER_SAMPLE_TYPES` | 31 |
| Clinical domain list | `CLINICAL_DOMAINS` | 33 |
| Domains locked to cross-sectional | `ALWAYS_CROSS_SECTIONAL` | 72 |
| Domains defaulting to longitudinal | `DEFAULT_LONGITUDINAL` | 77 |
| Domains prompting for an instrument name | `NEEDS_SPECIFYING` | 80 |
| The screen-2 design matrix | `design_matrix` / `design_section` |  |
| Example cohort DNA numbers | `DEMO_DNA` |  |
| Cap on projected years | `MAX_PLAN_YEARS` | 83 |
| Nudge threshold (currently 50%) | `NUDGE_THRESHOLD` | 82 |
| Default dates and status | `DEFAULT_META` | 97 |
| Screen order, names, adding a screen | `STEPS` | 794 |
| Demo data | `load_demo()` | 568 |

The four lists at the top are the ones Lietsel is most likely to want to edit. They are plain Python lists and dicts — no code changes needed to add, remove, or rename an item. Everything downstream (grids, validation, export) is generated from them.

### Function map

| Function | Does |
|---|---|
| `screen_cohort` … `screen_gp2_view` | One per screen. Self-contained; edit in isolation. |
| `plan_years` | The projected years. Empty for a completed study — everything downstream keys off this. |
| `design_of` | Cross-sectional or longitudinal for a domain, honouring the locked set. |
| `items_for` / `items_assigned` | Which items of a kind a phenotype has, and the reverse. |
| `design_matrix` | The screen-2 matrix: one `st.segmented_control` per item × phenotype. |
| `base_design` | The starting value each cell opens at. |
| `item_screen` | Screens 4 and 5 share this. Biosamples and clinical domains differ only in labels and whether DNA pre-fill applies. |
| `dna_prefill` / `apply_prefill` | Seed clinical grids from the DNA plan. Cumulative-before-the-year logic for follow-up columns lives in `dna_prefill`. |
| `value_columns` | **The shape of every grid.** Decides which of Baseline / `<year> new` / `<year> follow-up` / Follow-up N appear. |
| `make_grid` / `grid_config` | Build the frame and its column types. |
| `carry_over` | Preserves typed values when the row or column set changes. |
| `melt_grid` / `to_long` | Assemble the long export. **The storage schema is defined here.** |
| `validate` | Returns `(errors, warnings)`. Errors block, warnings do not. |
| `dna_totals` | DNA participants per phenotype. Used by coverage and validation. |

---

## Common changes

**Add or rename a clinical domain** — edit `CLINICAL_DOMAINS`. Nothing else. If it should never repeat, add it to `ALWAYS_CROSS_SECTIONAL`; if it usually repeats, add it to `DEFAULT_LONGITUDINAL`.

**Choosing a control on screen 2.** Three designs were tried and two were wrong. `SelectboxColumn` costs two clicks to change a value — wrong for the most-repeated action in the app. Two checkboxes ("collected" plus "LT") are one click each but can express a contradiction — unticked collected with ticked LT — which is worse than the extra click. `st.segmented_control` is one click, sets the value directly, and cannot represent a meaningless state. Use it for anything with three states, and don't reintroduce a coarser cohort-wide layer above it: that was tried, and it duplicated the same question at a grain nobody needed.

Cost to watch: one control per item × phenotype, each click a full rerun. 160 controls is the realistic upper end.

**Change which columns a grid asks for** — `value_columns()`, plus the `new_years` / `followup` flags at the call site. This is the single lever for the whole baseline/new/follow-up shape.

**Add a column to the grids** — three places, in order: `make_grid` (the column), `grid_config` (its type and help), and `melt_grid` (recognising it, via `numeric_cols` if it is a count). Missing the third is the usual bug: the column shows in the UI but never reaches the export.

**Change what counts as a lagging cohort** — `screen_gp2_view`, the `lag` and `overdue` lines. Participants and follow-up are checked separately on purpose.

**Change a validation rule** — `validate()`. Prefer warnings to errors; PIs abandon forms that block them. Negative numbers are prevented at the widget, not validated afterwards.

---

## Deliberate omissions

Not oversights. Each needs a decision before real use.

| Missing | Note |
|---|---|
| **Authentication** | REDCap is unavailable and PIs will not create accounts. Plan on per-cohort tokenised links. |
| **Persistence** | Drafts save/load as JSON files by hand. Real use needs Sheets, BigQuery, or Firestore behind `to_long()`. |
| **Deadline scheduling** | Year deadlines reuse the first deadline's month and day. Real use may need per-year dates. |
| **Notifications** | The tracking screen identifies who to nudge. It does not send anything. |

---

## The one trap to stay out of

**Never feed a widget's own output back in as its input.** Both bugs found so far were this same mistake in two shapes:

```python
# BROKEN — editor's output becomes its input next rerun
st.session_state["samples"] = st.data_editor(build_grid(...), key="ed")

# BROKEN — multiselect's output becomes its `default` next rerun
scope["phenotypes"] = st.multiselect("...", PHENOTYPES, default=scope["phenotypes"])
```

Streamlit keeps a widget's pending change as a diff against the object or default it was handed. Hand it something new on the next rerun and the widget is treated as new, so the pending change is discarded — every value has to be entered twice, and multiselects cannot be built up one item at a time.

The pattern used throughout instead:

- **Widgets own their value via `key`.** No `value=`, no `default=`, no `index=` computed from state we also write to.
- `sync_from_widgets()` derives `meta` and `scope` from those keys once per run, in `main()`. Those dicts are read-only for the rest of the app.
- Grids get a cached frame from `editor_source()` that is the *same object* every rerun; the editor's return value goes to a different session key.

If a new widget needs to be added, follow this. A `default=` wired to mutable state will reintroduce the bug somewhere far from where it is typed.

### The other half: state does not survive navigation on its own

Streamlit discards the session_state entry for any keyed widget that was **not rendered on the previous run**. It survives one rerun, then goes. So a `key=`-backed widget on screen 2 loses its value once the user has been on screen 3 for two reruns — which is what made screen 3 insist that no phenotypes had been selected.

Two mechanisms handle this, because plain widgets and data editors differ:

- **Plain widgets** (`w_*`): `persist_widget_state()` re-assigns each key at the top of `main()`, before anything renders. That marks them as still in use. Add any new widget key to `WIDGET_KEYS` or it will silently reset.
- **Data editors**: their state *cannot* be re-assigned — Streamlit does not allow setting `st.session_state` for `st.data_editor`. Instead `_nav` (bumped in `main()` when the step changes) is folded into every editor signature, so returning to a screen rebuilds the frame from the stored output. Values are restored and the widget starts clean. `_nav` is constant while you stay on a screen, so the frame remains the same object and edits still land on the first try.

## Known rough edges

- **Biosamples have no new-per-year column.** Screen 4 asks Baseline N plus follow-up per year. A sample from someone recruited in year 3 has no obvious home. Unresolved — §10.1 of the spec.
- `n_followup` counts *participants contributing a repeat*, not observations. Visits per person is not captured beyond the free-text interval.
- Domains needing an instrument named (Depression, Smell testing, QUIP, PDQ-8/39) rely on free text in the note column, so they are not analysable without cleanup.
- The design matrix renders every item × phenotype. No pagination or virtualisation — large cohorts may feel sluggish.
- Projected years are capped at `MAX_PLAN_YEARS`; longer studies are silently truncated.
- Clinical grids are keyed `(phenotype, design)`. Flipping a domain between cross-sectional and longitudinal moves it to the other grid and its typed numbers do not follow.
- `design_matrix` seeds each `seg::` key from the store when absent, never via `default=`. That both avoids the output-as-input trap and survives Streamlit garbage-collecting the keys on navigation. Adding a `default=` there would reintroduce both bugs at once.
- Prefill fires once per `(kind, phenotype, design)` grid, tracked in `_prefilled`, and only on rows that are entirely zero. Loosening either condition means DNA edits start clobbering numbers the PI typed. The `kind` in that key matters: without it screens 4 and 5 collide on `PD||Longitudinal` and whichever is visited first silently blocks the other.
- Both screens seed from DNA, with different wording in `PREFILL_NOTE`. Biosample coverage is usually well below the genotyped count, so that note tells the PI to expect to reduce the numbers rather than confirm them.
- `domain_grid` deliberately does **not** call `carry_over`. `designs` and `domain_phenotypes` are the authoritative store and are refreshed from the editor every run; merging the cached frame back in silently undoes the PI's last change. The count grids are the opposite case — there the cached value *is* the store, so they do use it.
- Only completed, released material is visible to GP2, so percentages below 100% before a deadline are normal. That is why the nudge needs both an overdue deadline and a low percentage.
- Acronyms carried over unverified: "CBFS A", "MERQ-PD" vs "mMERQ-PD", "PSG RBD". The source list wrote MDS-UPRDS; read as MDS-UPDRS.

## Style

Plain Streamlit, no custom CSS, no component libraries. `st.data_editor` grids rather than stacks of individual number inputs — it is much faster to fill and it matches the long storage format row for row. Keep it that way; the point of the prototype is the interaction design, not the styling.
