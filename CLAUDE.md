# GP2 transfer plan app — handover notes

Everything in one file: `code/transfer_plan_app.py` (~600 lines). No database, no auth. Prototype for discussion, handed over as the starting point for real development.

```
pip install -r requirements.txt
streamlit run code/transfer_plan_app.py
```

Click **Load an example cohort** in the sidebar to see it populated.

This file doubles as the instruction file for Claude Code. Read it before changing anything.

---

## What the app does

Cohort PIs declare how many **participants** they will transfer, per phenotype, per material, per clinical instrument, by a deadline. GP2 compares that against what arrives and nudges the cohorts that lag badly.

Full requirements live in `README.md` — read it first for the *why*. This file is only about the code. `README.md` §11 also has two specific recommendations for the next iteration (a template-CSV entry workflow, and capturing the whole multi-round plan up front rather than one snapshot at a time) that aren't built yet — worth reading before starting new work here.

---

## How this file and README.md relate

**README.md is the specification.** It owns what the app should collect and why,
the reference lists, the storage schema, the open product decisions, and the
recommendations for what to build next. Edit README.md when you're deciding or
changing something about the *product* — resolving one of its open questions,
changing what's asked, adopting the plan/snapshot change in §11.2.

**This file is a map to the code, not a second copy of the spec.** It holds the
invariants the code must preserve (Five rules, below) and where to make common
changes. It gets loaded into every Claude Code session automatically, so keep
additions here about the code, not the product — a product decision belongs in
README.md, referenced from here by section number as needed.

**Update direction, in order:**

1. Decide or record the decision in README.md first.
2. Implement it in `transfer_plan_app.py`.
3. Update this file: the "Where to change what" line numbers and "Function map"
   if anything moved, and re-check whether any of the Five rules need revising
   given the new behavior — building README §11.2, for instance, will require
   changing Rule 3.
4. If you build one of README §11's recommendations, move it out of that section
   into the main numbered spec once it's real, so README doesn't keep describing
   a prototype that no longer matches the app.

A code change with no product decision behind it (a bug fix, a refactor) usually
only needs step 3. A spec change with no code behind it yet is just step 1 —
don't update this file for a decision that isn't built.

---

## Five rules that must not be broken

Changes that violate these are wrong even if they look like improvements.

1. **The unit is participants, counted once per item.** One person giving blood + plasma + DNA is +1 in each of those three rows. Never aliquots, tubes, or visits.
2. **DNA is the denominator.** DNA counts per phenotype define cohort size. Coverage is always derived from them, never asked as a question. This is why DNA has its own screen and comes first.
3. **Each round is a cumulative snapshot.** PIs report totals to date with the previous round shown read-only beside the input. Never ask for increments — deltas get miscounted and the error compounds silently across years. (This rule is about how one round is reported; README §11.2 recommends also capturing the whole multi-round plan up front, which is a separate, not-yet-decided change to the schema — read it before conflating the two.)
4. **Store long, present wide.** One row per `cohort × round × phenotype × item`. Never widen the storage schema to add a modality or a deadline. Wide tables are pivots at display time.
5. **Ask what exists, then ask numbers.** Scope screen first, grids filtered to what was selected. This is the entire reason the app exists rather than a form. A change that shows a PI items they did not select is a regression.

---

## Where to change what

| To change | Edit | Line ≈ |
|---|---|---|
| Phenotype list | `PHENOTYPES` | 21 |
| Biosample list (non-DNA) | `OTHER_SAMPLE_TYPES` | 28 |
| Clinical groups and instruments | `MODALITY_GROUPS` | 32 |
| Which scales are phenotype-gated | `PHENOTYPE_GATED` | 56 |
| Nudge threshold (currently 50%) | `NUDGE_THRESHOLD` | 67 |
| Default dates, round label | `DEFAULT_META` | 74 |
| Screen order, names, adding a screen | `STEPS` | 531 |
| Demo data | `load_demo()` | 568 |

The four lists at the top are the ones Lietsel is most likely to want to edit. They are plain Python lists and dicts — no code changes needed to add, remove, or rename an item. Everything downstream (grids, validation, export) is generated from them.

### Function map

| Function | Does |
|---|---|
| `screen_cohort` … `screen_gp2_view` | One per screen. Self-contained; edit in isolation. |
| `visible_instruments` | Applies the phenotype gate. The conditional-scoping logic lives here. |
| `build_grid` / `merge_grid` | Build the editable grid; `merge_grid` preserves typed values when scope changes. |
| `numeric_config` | Column types and help text. Also where the repeat column is added or hidden. |
| `to_long` | Assembles the long-format export. **The storage schema is defined here.** |
| `validate` | Returns `(errors, warnings)`. Errors block, warnings do not. |
| `dna_denominator` | Cumulative DNA per phenotype. Used by coverage and validation. |

---

## Common changes

**Add a clinical instrument** — add a string to the right list in `MODALITY_GROUPS`. Nothing else.

**Add a new clinical group** — add a key to `MODALITY_GROUPS`. It appears on the scope screen and gets its own expander automatically.

**Gate an instrument to a phenotype** — add an entry to `PHENOTYPE_GATED` mapping the instrument name to a set of phenotypes.

**Add a column to the grids** — three places, in order: `build_grid` (the column), `numeric_config` (its type and help), `to_long` (its rename and inclusion in `cols`). Missing the third is the usual bug: the column shows in the UI but never reaches the export.

**Change a validation rule** — `validate()`. Prefer warnings to errors; PIs abandon forms that block them. Negative numbers are prevented at the widget, not validated afterwards.

**Change the nudge rule** — `screen_gp2_view`, the `lagging` and `overdue` lines.

---

## Deliberate omissions

Not oversights. Full discussion and what each needs is in `README.md` §10–§11 — summary of what's missing from the code:

| Missing | Where it would plug in |
|---|---|
| **Authentication** | Nothing in the code identifies a PI; `meta["cohort_id"]` is free text. |
| **Persistence** | Drafts save/load as JSON files by hand (`sidebar()`'s file uploader / `screen_review()`'s download button). Real use needs a store behind `to_long()`. |
| **Deadline scheduling** | Ongoing studies generate a year list (`DEFAULT_META`) but only one round is editable at a time — no multi-round history. |
| **Notifications** | `screen_gp2_view()` identifies who to nudge. It does not send anything. |

---

## Known rough edges

- `n_repeat` currently means *participants returning*, not *observations*. This is unsettled — see §10 of the spec. If it becomes observations, `dna_denominator` comparisons in `validate()` stop being meaningful and need rethinking.
- Brain-only and autopsy cohorts legitimately have clinical data exceeding DNA counts. This fires a soft warning by design; do not turn it into an error.
- `merge_grid` matches on `(Phenotype, Item)`. Renaming an item in `MODALITY_GROUPS` silently drops any value a PI already typed for it.
- Only completed, released material is visible to GP2, so `pct_complete` below 100% before a deadline is normal and means nothing. That is why the nudge needs both an overdue deadline and a low percentage.
- Two proposed groups — "Core clinical minimum" and "Medication" — are additions to the original leadership list, not part of it. Delete them if leadership says no.
- Acronyms carried over unverified: "Epworth Sleepiness Scale" (original list said "Sleeping"), "MERQ-PD-8", "PD RFU-Q", "CBFS". Both MDS-UPDRS and original UPDRS are listed — assumed deliberate for legacy data.

---

## Style

Plain Streamlit, no custom CSS, no component libraries. `st.data_editor` grids rather than stacks of individual number inputs — it is much faster to fill and it matches the long storage format row for row. Keep it that way; the point of the prototype is the interaction design, not the styling.
