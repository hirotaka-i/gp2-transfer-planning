# The vocabulary

Everything the apps know about GP2's clinical domains, instruments and
biosamples. **Most changes to the apps are edits in here, not in the code.**

The model behind these files — why there are three levels and why L1 and L2 are
not mapped to each other directly — is in [`../docs/DESIGN.md`](../docs/DESIGN.md).
This file is the column-by-column reference.

| File | Rows | Maintained by |
|---|---|---|
| `gp2_L1_constructs.csv` | 34 | **Hand.** The Stage 1 question list. |
| `gp2_L2_to_L1.csv` | 71 | Generated from the data dictionary, then hand-checked. |
| `gp2_L3_item_tags.csv` | 372 | Generated, then reviewed item by item. |
| `gp2_biosamples.csv` | 14 | Hand. |
| `gp2_omics.csv` | 15 | Hand. |
| `pending_modalities.txt` | — | Hand. Modalities the app names before the dictionary has them. |

After any data dictionary release, run `python check_vocab.py` from the repo
root. It reports what changed and what that breaks. It never edits these files.

---

## `gp2_L1_constructs.csv` — the Stage 1 question list

One row per domain a PI is asked about. This is the file to edit for anything a
cohort sees on Stage 1 screen 3.

| Column | Values | What it does |
|---|---|---|
| `category` | History · Diagnosis & course · Clinical assessment · Imaging · Biomarker · Neuropathology | Groups the matrix into blocks. Row order within the file sets display order. |
| `l1` | 34 unique | The domain name shown to the PI, and the key everything else joins on. **Renaming one means updating `extra_l1` in the tags file and `INSTRUMENT_GROUPS` in the Stage 2 app.** |
| `type` | `construct` (28) · `instrument` (6) | Whether the concept has competing scales or effectively one tool. Documentation for editors; the apps do not branch on it. |
| `default_on` | `1` (13) · `0` (21) | Whether the row starts ticked. The single most useful knob — a cohort holding only the common domains should touch nothing. |
| `ask_at_stage1` | `1` | Reserved. Everything is asked at Stage 1 today. |
| `phenotype_scope` | `all` · `case` · `atypical` | `case` hides the domain for control arms; `atypical` hides it for PD, Control and Population Control. |
| `fixed_design` | `Cross-sectional` or blank | When set, the LT option is not offered. Used for Demographics, Family history and Pathology — collected once per person however long the study runs. |
| `in_dictionary` | `True` · `False` | `False` marks the row with ⚠︎ and excludes it from Stage 2. CT, MRI and PET: asked so the answer is captured, but no schema exists to plan a transfer against. |
| `examples` | free text | The caption under the domain name. Half hand-written, half generated from the L2 map and item tags (`· also appears inside: …`). This is where a PI works out whether they hold the domain, so it is worth getting right. |
| `note` | free text | Editor-facing only. Not displayed. |

**Adding a domain:** add a row. It appears on Stage 1 immediately. For it to be
plannable at Stage 2 it also needs at least one entry in `INSTRUMENT_GROUPS`.

---

## `gp2_L2_to_L1.csv` — instrument to domain

One row per data dictionary modality. Generated from the dictionary; edit when
the dictionary changes.

| Column | What it does |
|---|---|
| `l2_modality` | The modality name, **exactly** as the dictionary spells it. This is the join key — a whitespace difference breaks it silently. |
| `n_items` | How many dictionary items it holds. Informational; `check_vocab.py` does not enforce it. |
| `primary_l1` | Its home domain, or `EXCLUDE`, or `MULTIPLE`. |
| `note` | Editor-facing. For disease-specific scales it records the phenotype. |
| `requires_item_tags` | `1` for the 17 cross-cutting instruments whose items need individual tags. |

Two special values of `primary_l1`:

- **`EXCLUDE`** — `Base` (participant IDs, visit numbers) and `Availability`
  (already covered by the biosample question). Never offered in either app.
- **`MULTIPLE`** — `MERQ-PD-B`, `Modified MERQ-PD`, `PD RFQ-U`. No home domain,
  so every one of their items must be tagged individually in the file below.
  ([Why](../docs/DESIGN.md#primary_l1--multiple).)

---

## `gp2_L3_item_tags.csv` — which items serve which domains

One row per (item, extra domain). An item with two extra domains has two rows.
Only the 17 cross-cutting instruments appear here; everything else inherits its
modality's `primary_l1`.

| Column | What it does |
|---|---|
| `item` | Dictionary item name. Join key. |
| `l2_modality` | The form it sits on. |
| `primary_l1` | Its modality's home domain, copied for readability. |
| `extra_l1` | The additional domain this item serves. **Empty means "reviewed, nothing to tag" — not "not looked at yet".** |
| `strength` | `secondary` or `incidental` |
| `source` | `auto+accepted` · `review` · `reviewed` — how the row got its value. |
| `needs_review` | `0` throughout. Set to `1` if you add rows that still need a human. |

**The empty `extra_l1` rows are load-bearing.** 214 of the 372 rows are items
someone looked at and decided carried no extra domain. Deleting them would make
`check_vocab.py` flag every one as a new untagged item. Keep the row, clear the
tag.

`strength` is `secondary` (a real subscale or block of items) or `incidental`
(one item in passing). `primary` is implied by `primary_l1` and never stored
here. Stage 2 uses it to decide which instruments start ticked —
[what the three levels mean](../docs/DESIGN.md#tag-strength).

---

## `gp2_biosamples.csv` and `gp2_omics.csv`

`biosample` / `note` and `assay` · `tissue` · `label` · `note`. Both are plain
lists; add or remove rows freely.

Two things to know:

- **`DNA` is special.** It has its own screen in Stage 2 and sets the
  denominator for every coverage figure, so it is filtered out of the "other
  biosamples" lists in code. Do not rename it without checking `dna_basis()`.
- **`RNA (Tempus tube)` is flagged in its `note`** as not appearing in the
  reviewed biosample list. It is included pending confirmation — the Site
  Interest Form asks for it and the dictionary has `availability_rna`, so
  dropping it would lose the answer. Remove the row if GP2 confirms it is not
  wanted.

`label` in the omics file is what the PI sees; `assay` and `tissue` exist so the
list can be regenerated as a cross product.

---

## `pending_modalities.txt`

One modality name per line, `#` for comments. Names the app uses before the data
dictionary has them, so `check_vocab.py` reports them as pending rather than
broken. Currently one entry: `Mortality`, which GP2 will split out of
`PD History`. Delete the line once that lands.

Without this file the checker fails on every run, which trains people to ignore
it.
