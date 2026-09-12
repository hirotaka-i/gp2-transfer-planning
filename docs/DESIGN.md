# Design

Why the model looks like this. Read once before changing anything structural;
`CLAUDE.md` covers day-to-day work.

---

## 1. The problem

GP2 collects two things from a cohort at two different moments, and until now in
two unconnected systems.

**Site Interest Form**, a Google Form of 129 questions, filled when a cohort
first makes contact. Roughly half of it is `sample type × phenotype × (current /
projected)` repeated — all of it shown to everyone, whether or not they have it.
Its purpose is to let GP2 decide genotyping versus sequencing.

**The transfer plan**, agreed months later when the DTA/MTA is drawn up. Firm
numbers, a schedule, and something GP2 can track arrivals against.

The two overlap heavily and disagree invisibly. A cohort that estimates 500
participants and later contracts for 200 leaves no record of the change anywhere.

---

## 2. Three levels of vocabulary

The GP2 Data Dictionary has 1009 items grouped into 71 modalities. A modality is
an **instrument** — `MoCA`, `PDQ-39`, `MERQ-PD-B`. That is the right unit for a
transfer plan: it is what a cohort physically administered and what GP2
harmonises.

It is the wrong unit for a first conversation. A PI knows they collect
"depression data"; whether GP2 calls the form `Geriatric Depression Scale: Short
Form` is not their concern yet. So Stage 1 asks at **construct** level.

```
L3  Item       1009   the dictionary's variables
L2  Modality     71   the instrument — what was administered
L1  Construct    34   the concept — what a PI can answer for
```

### L1 and L2 are different axes, not levels of one tree

This is the thing to understand before touching the vocabulary.

- **L2 is a partition of items.** Each item belongs to exactly one form.
- **L1 is a tag over items.** One item can serve several constructs.

Mapping L1 to L2 directly produces a many-to-many mess. Measured on the real
dictionary:

| Construct | Items | Modalities they sit in |
|---|---|---|
| Depression | 14 | **11** |
| Smoking | 18 | 4 |
| Head trauma | 9 | 5 |
| Anxiety | 8 | 7 |

`MERQ-PD-B` alone covers lifestyle, environment, head injury, depression and
surgical history. So the mapping is defined **at the item level** and any L1↔L2
relationship is derived from it. There is no hand-maintained correspondence
table to drift.

The files that hold this are documented column by column in
[`../vocab/README.md`](../vocab/README.md).

```
L3 Item ──(1:1)──→ L2 Modality      already in the dictionary
L3 Item ──(m:n)──→ L1 Construct     vocab/gp2_L3_item_tags.csv
```

### Tag strength

"Has depression data" is meaningless without it — a dedicated GDS-15 and a
single Likert item inside PDQ-39 are not the same claim.

| Strength | Meaning | Example |
|---|---|---|
| `primary` | The instrument exists to measure this | GDS-15 → Depression |
| `secondary` | A real subscale or block | MERQ-PD-B depression block |
| `incidental` | One item in passing | RBDSQ 10f, PDQ-39 #17 |

### `primary_l1 = MULTIPLE`

Three exposure questionnaires — `MERQ-PD-B`, `Modified MERQ-PD`, `PD RFQ-U` —
have no defensible home construct, so they are not given one. Every one of their
items must carry an explicit tag. `primary_l1` doubles as the default inherited
by untagged items, so an arbitrary choice there would silently mistag the rest
of the form. `MULTIPLE` removes the choice and makes the requirement checkable.

### Construct or instrument at Stage 1?

> Where a concept has effectively one instrument, ask by instrument. Where
> several instruments compete, ask by construct.

UPDRS, H&Y, CISI-PD, PSP-RS, UMSARS, SAA, DAT-SPECT are asked by name. Lifestyle,
environment, head trauma, depression, anxiety, cognition, pain are asked as
concepts, because the scales genuinely vary — the dictionary even has a
`Misc Depression Scale` modality for naming whatever was used. The `type` column
in `gp2_L1_constructs.csv` records which is which.

---

## 3. The two stages

| | Stage 1 | Stage 2 |
|---|---|---|
| Unit | L1 construct | L2 instrument |
| Numbers | now / projected total | baseline + per year |
| Status | estimate | commitment |
| Purpose | genotyping vs sequencing | schedule and tracking |

Both are **filled once**. Stage 1 at first contact; Stage 2 at contracting. An
ongoing study projects year by year rather than being asked to re-report
annually. That is why no screen shows "previously reported".

### Stage 1 → Stage 2 is suggestion, not derivation

The mapping is many-to-many, so Stage 1 cannot determine Stage 2 rows. Two
checks instead:

**Forward.** Stage 1 constructs → the instruments serving them, pre-selected.
The instrument most cohorts use is ticked, the alternatives are listed unticked.

**Backward.** The plan → the constructs it actually covers → compared against
what Stage 1 claimed. This is the reconciliation table on the review screen:
number differences per phenotype × sample, domains reported but not carried,
domains reported longitudinal that arrive cross-sectional, phenotype changes in
both directions.

Nothing blocks. Stage 1 is an estimate made months earlier, often by someone
else; disagreement is expected. The value is that the change becomes visible,
which it is not today.

### Seeding rules

Defaults matter more than they look — a PI who has to correct thirty cells will
correct three and leave the rest.

- **Stage 1 timespan seeds the domain matrix.** Cross-sectional → all CS.
  Longitudinal → all LT. Cross-sectional plus → CS except mortality and disease
  course, which is exactly what "plus" means.
- **Demographics, family history and pathology are locked cross-sectional.** A
  ten-year cohort still records demographics once.
- **Only 13 of 34 domains start ticked**, chosen as the ones most cohorts hold.
- **Stage 2 inherits CS/LT from Stage 1** per (instrument, phenotype). An
  instrument serving several constructs takes the strongest answer.
- **Explicitly added things never open at `None`.** A free-text measure the PI
  typed, or an instrument from a domain Stage 1 never mentioned, opens at CS. A
  domain Stage 1 reported as absent for a phenotype still opens at `None`.
- **Disease-specific scales open at `None` outside their own phenotype.** A PSP
  rating scale is not "cross-sectional in the PD arm"; it is not collected there.
- **Counts pre-fill from DNA.** Matching columns copy across; follow-up columns
  take the cumulative enrolment available to be seen again that year. Baseline
  400 plus 200 new in 2026 means 2027 follow-up opens at 600. Only rows that are
  still entirely zero are touched, once, so later DNA edits never overwrite
  typed numbers.

### The DNA denominator

Coverage is always participants-for-an-item over participants-with-DNA for that
phenotype. Which sample supplies that count depends on Stage 1:

| Stage 1 | Denominator from |
|---|---|
| Extracted DNA available | DNA |
| Extraction needed, source = Blood | blood |
| … Saliva / Brain / Other | that sample |

Stage 1 enforces the consistency: claiming extracted DNA without DNA in the
biosample list, or extraction from saliva without saliva in the list, are errors.

---

## 4. Storage schema

One row per `phenotype × item × period`. Long, not wide.

```
cohort_id, contact_name, contact_email, study_status,
phenotype, item_class, item, dictionary_modalities, design,
period, deadline, n_new, n_followup, n_total, interval, note
```

`period` is `baseline` or a year, which is what carries the projection. Adding an
instrument, a phenotype or a year never changes the schema; any wide view
leadership wants is a pivot.

`dictionary_modalities` records which underlying modalities a row covers, so a
plan attached to a DTA/MTA is unambiguous about what will actually arrive.

---

## 5. Keeping up with the data dictionary

`check_vocab.py` compares the vocabulary against the dictionary, by default
fetching it from GitHub. It reports modalities added, removed, or referenced but
gone; likely renames by string similarity; new items in cross-cutting
instruments that carry no tag yet; tagged items that have moved to another form.

It is **read-only**. About a third of the item tags and all of
`INSTRUMENT_GROUPS` are human judgement a diff cannot reproduce, so the checker
reports and exits non-zero; a person decides what a change means.

Rows in `gp2_L3_item_tags.csv` with an empty `extra_l1` are deliberate: they
record "reviewed, nothing to tag", which is what lets the checker tell a new
item apart from one already considered.

**Worth asking GP2 for:** a stable `modality_id` and `item_id` in the dictionary.
Renames are currently indistinguishable from a delete plus an add, and that is
the one problem the app cannot solve on its own. Construct columns in the
dictionary are *not* worth asking for — L1 is an app-level concept on a different
release cycle, and the strength tags are per-item.

---

## 6. Deliberate omissions

| Missing | Note |
|---|---|
| Persistence | Stage 1 → JSON → Stage 2 by hand. The production design is a GP2 study code issued at the end of Stage 1, used as the key to load Stage 2. |
| Authentication | Per-cohort tokenised links. Stage 1 is a first contact, so friction there costs submissions. |
| Notifications | The plan identifies what is due; nothing sends anything. |
| Arrival tracking | A tracking screen existed and was removed as out of scope for the prototype. Recoverable from git history if it is wanted later. |
