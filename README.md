# GP2 Data & Sample Transfer Plan — Input Specification

Draft v0.1. Written for internal discussion, now handed over to Lietsel as the
starting point for real development. Companion spec to `code/transfer_plan_app.py`;
for how that code is organized, see `CLAUDE.md`.

## Quick start

```
pip install -r requirements.txt
streamlit run code/transfer_plan_app.py
```

Click **Load an example cohort** in the sidebar to see it populated. The last
sidebar item is the GP2 tracking view — the "who is lagging" screen.

This is a prototype for discussion, not a live collection tool: no auth, no
database, no real persistence. See §11 for what that means for what's next.

---

## 1. What this collects and why

Cohort PIs declare **how many participants** they will transfer, **for each material and each clinical modality**, by an agreed deadline. GP2 then compares those declarations against what actually arrives, and nudges the cohorts that fall a long way behind.

Two consequences shape every design decision below:

- This is a **register, not a survey**. Ongoing cohorts return to it once a year and revise their own numbers. The record has to carry history.
- The comprehensive list leadership wants and the burden a PI will tolerate are only reconcilable through **conditional scoping** — ask what exists first, then ask numbers only for that. A flat instrument asks 765 cells; a typical cohort should see about 45.

Out of scope: consent, MTA/DTA terms, de-identification, harmonisation format, shipping logistics. All of these are settled in the MTA/DTA process or by GP2-defined transfer formats, and none of them belong in this app.

---

## 2. Definitions — settle these before building

**Unit of counting is always participants, counted once per item.**
One person contributing blood, plasma and DNA is `+1` in the blood row, `+1` in the plasma row, and `+1` in the DNA row. Never aliquots, tubes, or visits.

**DNA sets the denominator.** DNA counts per phenotype define the cohort size. Every coverage figure is derived against it, so DNA is asked first, on its own screen. Coverage is never asked as a question.

**Each round is a cumulative snapshot.** For ongoing studies, a PI reports the **total to date**, not the increment since last time. The previous round's number is shown read-only beside the input so they revise upward rather than compute a delta. This is self-correcting: a mistake in one round is fixed in the next, and no double counting is possible.

**New vs repeat.**
- `n_new` — participants contributing this item for the first time.
- `n_repeat` — participants **already transferred** who contribute a further assessment or draw.

> **Open question for us, not for Lietsel:** is `n_repeat` counted as *participants returning* or as *observations*? The prototype assumes participants, which keeps the DNA denominator coherent. But 30 people × 2 visits and 30 people × 8 visits are very different datasets for progression modelling. See §8.

---

## 3. Screen 1 — Cohort and study

| Field | Type | Required | Rules |
|---|---|---|---|
| `cohort_id` | text | yes | GP2-registered cohort ID. **Pre-filled** from our records. |
| `pi_name` | text | yes | **Pre-filled**. |
| `study_status` | radio: `Ongoing` / `Completed` | yes | Drives the whole downstream form. |
| `final_collection_year` | integer | if Ongoing | Current year … +20. Generates the annual deposit schedule. |
| `deadline` | date | yes | Completed → single date. Ongoing → deadline for this year's deposit. |

**Behaviour.** Selecting `Ongoing` generates one deposit round per year through `final_collection_year` and reveals the new/repeat split on later screens. Selecting `Completed` collapses the form to a single deposit with a single total column.

**Recommendation:** anchor deadlines to the **MTA/DTA execution date** (e.g. "first deposit 6 months after execution") rather than to fixed calendar dates. It removes a whole class of "we're late but the paperwork wasn't signed" disputes.

---

## 4. Screen 2 — Scope

This is the screen that makes the rest tolerable. Nothing here asks for a number.

| Field | Type | Required | Options |
|---|---|---|---|
| `phenotypes` | multiselect | ≥ 1 | The 17 GP2 phenotypes, §7.1 |
| `sample_types` | multiselect | optional | 7 non-DNA biosamples, §7.2 |
| `modality_groups` | multiselect | optional | 14 clinical domains, §7.3 |
| `show_all_instruments` | checkbox | default off | Override for the phenotype gate below |

**Live feedback.** As selections are made, show the cell count the PI is committing to versus the full grid. This is the single most persuasive element of the app and it costs one line of arithmetic.

**Pre-fill what we already know.** Phenotypes present can be seeded from existing GP2 genotyping data, which turns the task from entry into confirmation.

---

## 5. Screens 3–5 — The numbers

All three screens use the same editable grid. Rows are `phenotype × item`; the PI types into two or three columns.

| Column | Type | Editable | Notes |
|---|---|---|---|
| Phenotype | text | no | |
| Item | text | no | |
| Group | text | no | Clinical screen only |
| Previously reported | integer | no | Cumulative total from the last round; blank on first use |
| **New participants** | integer ≥ 0 | yes | |
| **Repeat participants** | integer ≥ 0 | yes | **Only rendered when `study_status = Ongoing`** |
| Note | text | yes | Optional. Free text, used at nudge time to learn *why* something is late |

### 5.1 Screen 3 — DNA

One row per selected phenotype. No repeat column (DNA is one-time per participant). Displays the running cumulative total, labelled explicitly as the denominator for everything that follows.

### 5.2 Screen 4 — Other biosamples

Rows = `selected phenotypes × selected sample types`. Skipped entirely if no non-DNA samples were selected.

### 5.3 Screen 5 — Clinical data

Rows = `selected phenotypes × instruments within selected groups`, one collapsible section per group.

**Ask at group level, name instruments only where the distinction matters to us.** The PI should not have to declare instruments we never branch on. Where we genuinely need the instrument (MDS-UPDRS vs original UPDRS, MoCA vs MMSE, the disease-specific criteria), it is named; elsewhere the group is enough.

**Phenotype gating.** These instruments are hidden unless a relevant phenotype is in scope:

| Instrument | Shown only if cohort includes |
|---|---|
| MDS-PSP criteria, PSP-RS, PSP-CDS | PSP |
| MDS-MSA criteria, UMSARS | MSA |
| CBS-Armstrong criteria, CBFS | CBD/CBS |
| DLB diagnostic criteria | DLB or LBD |

`show_all_instruments` overrides this for the PI who insists on seeing everything.

---

## 6. Not asked — derived or supplied by GP2

| Field | Source |
|---|---|
| `n_cumulative_participants` | `n_previous_cumulative + n_new` |
| Coverage % | `n_cumulative_participants ÷ DNA participants for that phenotype` |
| `n_received`, `received_date` | GP2 receiving side. **Never shown to or editable by the PI.** |
| `pct_complete` | `n_received ÷ n_cumulative_participants` |
| Nudge flag | `deadline` passed **and** `pct_complete < 50%` |

On the nudge threshold: because only completed, released material is visible to us, partial percentages before a deadline are normal and mean nothing. The flag deliberately fires on badly lagging items after a deadline, not on anything short of 100%.

---

## 7. Reference lists

### 7.1 Phenotypes (17)
PD · Control · PSP · DLB · MSA · CBD/CBS · FTD · AD · Mix · VaD · VaPD · Population Control · Undetermined-MCI · Undetermined-Dementia · Prodromal · Other · LBD

### 7.2 Biosamples
DNA (separate screen) · blood · serum · plasma · csf · brain · skin · SAA

### 7.3 Clinical modality groups and instruments

| Group | Instruments |
|---|---|
| Core clinical minimum *(proposed addition)* | Demographics, age at onset, diagnosis date, family history |
| Medication *(proposed addition)* | Medication log / LEDD |
| Motor | MDS-UPDRS, UPDRS (original), Hoehn & Yahr, CISI-PD, Schwab & England ADL |
| Cognitive | MoCA, MMSE, other cognitive battery |
| Autonomic | SCOPA-AUT, orthostatic hypotension, vital signs |
| Sleep | RBD questionnaire, Epworth Sleepiness Scale |
| Mood & behaviour | GDS, QUIP-RS, QUIP-CS |
| Olfaction | Olfactory test |
| Quality of life & pain | PDQ-39, pain scale |
| Imaging & functional | DAT results, MIBG results |
| Neuropathology | Pathology report |
| Disease-specific scales | MDS-PSP, PSP-RS, PSP-CDS, MDS-MSA, UMSARS, CBS-Armstrong, CBFS, DLB diagnostic criteria |
| Screening & other | IDEA screening questionnaire, PD RFU-Q, MERQ-PD-8 |
| Lifestyle & environment | Lifestyle, environment |

The two groups marked *proposed* are additions to the original list — demographics and medication are the fields most analyses need first, and they are currently absent. Flagging rather than assuming.

---

## 8. Storage schema

One row per `cohort × round × phenotype × item`. Store long, present wide.

```
cohort_id, round_label, as_of, study_status, deadline,
phenotype, item_class, item_group, item,
n_previous_cumulative, n_new, n_repeat, n_cumulative_participants,
n_received, pct_complete, note
```

`item_class` ∈ {`sample`, `clinical`}.

Adding a modality, a phenotype, or a deadline never changes the schema. Any wide table leadership wants is a pivot. The `round_label` / `as_of` columns give annual history for free.

---

## 9. Validation

**Hard (blocks submission)**
- `cohort_id` present
- At least one non-zero number
- DNA numbers entered for every selected phenotype
- Valid deadline

**Soft (warns, does not block)**
- Any item's cumulative count exceeds that phenotype's DNA count → likely a participant set outside the genotyped cohort, or an error. Warn rather than block: brain-only and autopsy cohorts legitimately break this.
- `study_status = Ongoing` but every `n_repeat` is zero
- Deadline in the past

Negative numbers are prevented at the input widget rather than validated after the fact.

---

## 10. Open decisions

Still open — flag to GP2 leadership before locking behavior:

1. **Repeat unit** — participants returning, or observations? If we want progression-modelling value, add one column for **expected observations per repeat participant** (or expected follow-up years) on the longitudinal groups only, i.e. motor and cognitive. Cheap now, impossible to reconstruct later.
2. **Brain-only cohorts** break the DNA denominator. The soft warning handles it, but expect it to fire.
3. **Acronyms to confirm before this reaches PIs** — "Epworth Sleepiness Scale" (the original list says "Sleeping"); "MERQ-PD-8"; "PD RFU-Q"; "CBFS A". Also confirm that listing both MDS-UPDRS and original UPDRS is deliberate, for legacy data.

For whoever builds the real version — this is now you, Lietsel:

4. **Authentication.** REDCap is not available to GP2, and PIs will not create accounts. Plan on per-cohort tokenised links.
5. **Save and resume** is non-negotiable. No PI completes this in one sitting.
6. **Persistence** — Sheets, BigQuery, or Firestore behind the app. The app is a UI over a table, not a store. See §11.1 for a lighter-weight interim step.
7. **Ownership.** Whoever builds this maintains it for the life of the consortium. Worth naming a person now.

---

## 11. Recommendations for the next iteration

The prototype (§12) proves the interaction design — conditional scoping, cumulative
totals, the coverage/nudge logic. Two things about *how numbers get in and out* are
worth changing before this becomes real, ahead of tackling auth/persistence above.

### 11.1 Move data entry off-screen: template CSV, not a live grid

Right now a PI fills numbers directly into `st.data_editor` grids in the browser
session. Instead:

- After the scope screen, generate a **CSV template** — one row per `phenotype × item`
  for exactly what was scoped, columns matching the long-format schema (§8) plus
  `n_new` / `n_repeat` for the PI to fill in. This is a small extension of the
  "Download plan (CSV)" button already on the review screen (`screen_review()`),
  generated earlier in the flow and blank instead of filled.
- The PI fills it offline, in whatever tool they already use, and **uploads it back**.
- On upload, the app runs the same validation it runs today (§9) plus a
  **consistency check against GP2's internal records** — DNA counts, received
  counts — once GP2 supplies that data as an input to the app. Errors surface before
  the PI's numbers are treated as submitted, not after.

Why this is worth doing before persistence: the app still never touches or stores
private data — only the PI's own CSV round-trips through it — so a single shared
Streamlit link stays sufficient. This does not require standing up a backend first;
it's a QC layer on top of file upload/download, which the app already does for the
JSON draft (`sidebar()`'s "Resume a saved draft" uploader is existing prior art for
the pattern).

Open for Lietsel to decide: the exact template schema (mirror `to_long()`'s columns
directly, most likely), how GP2's internal reference data reaches the app for the
consistency check each time, and how QC failures are shown back to the PI —
inline in the app, or as an annotated CSV to re-download and fix.

### 11.2 Capture the whole plan, not just one round's snapshot

Rule 3 in `CLAUDE.md` (each round is a cumulative snapshot) is right for *how a
single round's number is reported* — but today the app only ever asks for the
round in front of the PI right now. There is no view of, or place to declare, the
whole multi-year plan through `final_collection_year` at once.

Recommendation: have the PI declare their **intended cumulative totals for every
future round up front** — a plan — and then, each round, update *actuals* against
that plan rather than re-declaring numbers from nothing. The tracking screen
(`screen_gp2_view()`) already treats "promised vs. received" as the interesting
comparison for GP2; extending that same idea to "planned vs. actual" per round, per
PI, is a natural fit.

This is a schema decision, not just a UI one — flag it before building. The
storage schema (§8) currently has one `round_label` meaning "the round being
reported." A plan/actual model needs either a `planned` vs `actual` flag on each
row, or a separate plan table (`cohort × phenotype × item × target_year`) that the
per-round actuals get compared against. Worth settling before persistence (§10.6)
is built, since the schema shape depends on this decision.

Open for Lietsel to decide: whether the plan itself is revisable after first
declaration (and if so, how that's versioned), and whether "plan vs. actual"
should replace or sit alongside the current "previous round vs. this round" view.

---

## 12. Prototype

`transfer_plan_app.py` implements everything above except §10 items 4–7 and the
§11 recommendations. See Quick start at the top of this file to run it. For how
the code is organized — where to change the phenotype list, add a clinical
instrument, and so on — see `CLAUDE.md`.
