# GP2 Data & Sample Transfer Plan — Input Specification

Draft v0.1 · for discussion with Lietsel · companion to the Streamlit prototype

---

## 1. What this collects and why

Cohort PIs lay out their **whole transfer plan once**, at contracting. For a completed study that is a single set of numbers. For an ongoing study they project **year by year** until collection ends. GP2 then compares the plan against what actually arrives and nudges the cohorts that fall a long way behind.

Two consequences shape every design decision below:

- This is an **up-front plan, not an annual re-report**. PIs are not asked to come back each year and revise, so nothing shows them what they said last time. The year dimension is a projection they make once.
- The comprehensive list leadership wants and the burden a PI will tolerate are only reconcilable through **conditional scoping** — ask what exists first, then ask numbers only for that.

Out of scope: consent, MTA/DTA terms, de-identification, harmonisation format, shipping logistics. All of these are settled in the MTA/DTA process or by GP2-defined transfer formats, and none of them belong in this app.

---

## 2. Definitions — settle these before building

**Unit of counting is always participants, counted once per item.**
One person contributing blood, plasma and DNA is `+1` in the blood row, `+1` in the plasma row, and `+1` in the DNA row. Never aliquots, tubes, or visits.

**DNA sets the denominator.** DNA counts per phenotype define the cohort size. Every coverage figure is derived against it, so DNA is asked first, on its own screen. Coverage is never asked as a question.

**Baseline vs new vs follow-up.**
- **Baseline N** — participants contributing this item at their own baseline. For a cohort already recruited, this is most of the plan.
- **`<year>` new** — participants expected to be recruited in that year and contribute this item. Only for ongoing studies.
- **`<year>` follow-up** — already-enrolled participants contributing a repeat in that year. Only for items marked longitudinal.

**Cross-sectional vs longitudinal is a property of the domain, not the study.** A cohort can run for ten years and still collect family history once. The PI marks each domain on screen 2, and that decides whether follow-up columns appear on screen 5. Three domains are locked cross-sectional: Demographics, Extended family history, Diagnosis (baseline).

---

## 3. Screen 1 — Cohort and study

| Field | Type | Required | Rules |
|---|---|---|---|
| `cohort_id` | text | yes | GP2-registered cohort ID. **Pre-filled** from our records. |
| `contact_name` | text | yes | Day-to-day contact for transfers, not necessarily the PI. |
| `contact_email` | text | yes | Must contain `@`. This is who gets nudged. |
| `study_status` | radio: `Ongoing` / `Completed` | yes | Drives the whole downstream form. |
| `final_collection_year` | integer | if Ongoing | Current year … +20. Sets how many year columns appear. |
| `deadline` | date | yes | Completed → the single transfer date. Ongoing → the first transfer deadline; later years reuse the same month and day. |

**Behaviour.** `Ongoing` generates one column per year from the deadline year through `final_collection_year`, capped at 10 years. `Completed` collapses every grid to a single Baseline N column, plus Follow-up N where the item repeats.

**Recommendation:** anchor deadlines to the **MTA/DTA execution date** (e.g. "first deposit 6 months after execution") rather than to fixed calendar dates. It removes a whole class of "we're late but the paperwork wasn't signed" disputes.

---

## 4. Screen 2 — Scope

This is the screen that makes the rest tolerable. Nothing here asks for a number.

| Field | Type | Required | Options |
|---|---|---|---|
| `phenotypes` | multiselect | ≥ 1 | The 17 GP2 phenotypes, §7.1 |
| `sample_types` | multiselect | optional | 7 non-DNA biosamples, §7.2 |
| `domains` | multiselect | optional | 32 clinical domains, §7.3 |
| `phenotype_designs` | per item × phenotype | yes | `—`, `CS` or `LT`, one click |

There are **two identical matrices** on this screen — one for biosamples, one for clinical domains. Biosamples carry the same question: blood may be drawn annually in the PD arm and once in controls.

### The domain matrix

Design is a property of the **(item, phenotype) pair**, not of the item alone. A cohort can follow MMSE longitudinally in PD and take it once in controls; the same applies to blood. If that is not expressible, the plan is simply wrong for one arm.

It is asked as **one matrix**: a row per item, a column per phenotype, and in each cell a single three-state control.

| Value | Meaning |
|---|---|
| `—` | Not collected in that arm |
| `CS` | Cross-sectional — once per person |
| `LT` | Longitudinal — repeated over time |

One click sets the state directly. Because the three states are one control rather than two checkboxes, there is no way to express a contradiction, and no state that means nothing.

**Every cell starts at a sensible default**, so a PI whose arms were assessed identically changes nothing and moves on. Defaults are `CS`, except: Demographics, Extended family history and Diagnosis (baseline), which are locked to `—`/`CS` because they cannot repeat; and Diagnosis change and Mortality / living status, which start at `LT` because they are follow-up events by nature.

There is no separate cohort-wide table. It duplicated the same question at a coarser grain and made the screen longer without making anything faster.

**Design decides the shape of screen 5.** Cross-sectional domains get participant counts only; longitudinal domains also get follow-up counts and a repeat interval.

- **Locked cross-sectional**: Demographics, Extended family history, Diagnosis (baseline).
- **Defaulted longitudinal**, editable: Diagnosis change, Mortality / living status.
- Everything else defaults cross-sectional and the PI opts in.

**Live feedback.** The screen prints the cell count the PI is committing to versus the full grid, and it drops as they set cells to `—` — which is the clearest signal that answering this screen carefully saves them work later.

**Pre-fill what we already know.** Phenotypes present can be seeded from existing GP2 genotyping data, turning the task from entry into confirmation.

## 5. Screens 3–5 — The numbers

All three screens use editable grids. Rows are `phenotype × item`; the columns depend on study status and on the domain's design.

**Column sets**

| Screen | Completed study | Ongoing study |
|---|---|---|
| 3 · DNA | Baseline N | Baseline N + `<year> new` per year |
| 4 · Biosamples | Baseline N, Follow-up N | Baseline N + `<year> follow-up` per year |
| 5 · Cross-sectional domains | Baseline N | Baseline N + `<year> new` per year |
| 5 · Longitudinal domains | Baseline N, Follow-up N | Baseline N + `<year> new` and `<year> follow-up` per year |

Every grid also carries a free-text `Note`. Grids with follow-up carry `Repeat interval` — how often it repeats, e.g. "every 12 months".

### 5.1 Screen 3 — DNA

One row per selected phenotype. No follow-up: DNA is collected once per participant. For an ongoing study the year columns are **new recruits**, which is what makes the cohort grow. Running totals per phenotype are shown as the PI types.

**DNA also seeds screens 4 and 5.** Most cohorts assess nearly everyone they genotype, so zero is a poor starting value. Matching column names copy straight across, and follow-up columns get the cumulative enrolment available to be seen again that year — everyone recruited *before* it:

> Baseline 400, 200 new in 2026, 100 new in 2027 → 2026 follow-up starts at 400, 2027 at 600, 2028 at 700.

Seeding is deliberately conservative: only rows that are still entirely zero are touched, only once per screen and phenotype, and only after the DNA numbers for that phenotype are non-zero. A row the PI sets to zero stays at zero, and later DNA edits never overwrite typed numbers.

Both screens carry a visible instruction to correct anything that differs, because the risk of pre-filling is a PI accepting an optimistic number they never checked. The two are worded differently on purpose: clinical coverage is usually close to the genotyped count, biosample coverage usually is not, so screen 4 says to **expect to reduce most of these**.

### 5.2 Screen 4 — Other biosamples

Structurally identical to screen 5: organised by phenotype, split into cross-sectional and longitudinal grids according to the biosample matrix on screen 2. Cross-sectional samples get baseline plus per-year new; longitudinal ones also get per-year follow-up and a repeat interval.

This closes the earlier gap where biosamples had no `<year> new` column and a draw from someone recruited in year 3 had nowhere to go.

Seeded from the DNA plan like screen 5, with a stronger warning — see §5.1.

### 5.3 Screen 5 — Clinical data

**Organised by phenotype**, one expander per phenotype, with two grids inside: cross-sectional domains, then longitudinal ones. Which grid a domain lands in is decided per phenotype, so MMSE can sit in PD's longitudinal grid and in the control arm's cross-sectional one. A phenotype with no domains is skipped entirely.

Grids arrive pre-filled from DNA — see §5.1. This is the reverse of grouping by domain, and it matches how a PI thinks — they know their PD arm and their control arm, and the numbers differ by arm far more than by instrument.

Domains needing an instrument named (Smell testing, Depression, QUIP, PDQ-8/39) get a caption pointing at the note column.

## 6. Not asked — derived or supplied by GP2

| Field | Source |
|---|---|
| `n_total` | `n_new + n_followup` for a row |
| Coverage % | participants planned for an item ÷ DNA total for that phenotype |
| Per-year schedule | `deadline` reused with each projected year's month and day |
| `Received participants`, `Received follow-up` | GP2 receiving side. **Never shown to or editable by the PI.** |
| Participant % / Follow-up % | received ÷ planned, tracked separately |
| Nudge flag | deadline passed **and** either percentage below 50% |

The two receiving percentages are deliberately separate. A longitudinal domain can look complete on participants while every repeat assessment is still missing, and that is exactly the failure the tracking view exists to catch. The tracking view also aggregates by design, so cross-sectional and longitudinal completeness are never averaged together.

On the nudge threshold: only completed, released material is visible to GP2, so partial percentages before a deadline are normal and mean nothing. The flag fires on badly lagging items after a deadline, not on anything short of 100%.

## 7. Reference lists

### 7.1 Phenotypes (17)
PD · Control · PSP · DLB · MSA · CBD/CBS · FTD · AD · Mix · VaD · VaPD · Population Control · Undetermined-MCI · Undetermined-Dementia · Prodromal · Other · LBD

### 7.2 Biosamples
DNA (separate screen) · blood · serum · plasma · csf · brain · skin · SAA

### 7.3 Clinical domains (32)

Asked at domain level. Where the exact instrument matters, the PI names it in the note column rather than picking from a list we would have to maintain.

| # | Domain | Default design |
|---|---|---|
| 1 | Demographics | Cross-sectional (locked) |
| 2 | Extended family history | Cross-sectional (locked) |
| 3 | Diagnosis (baseline) | Cross-sectional (locked) |
| 4 | Diagnosis change | Longitudinal |
| 5 | Vitals | PI chooses |
| 6 | Medical history | PI chooses |
| 7 | Medication | PI chooses |
| 8 | Mortality / living status | Longitudinal |
| 9 | Environmental | PI chooses |
| 10 | SEADL | PI chooses |
| 11 | CISI-PD | PI chooses |
| 12 | MoCA | PI chooses |
| 13 | MMSE | PI chooses |
| 14–17 | MDS-UPDRS1, 2, 3, 4 | PI chooses |
| 18 | MERQ-PD | PI chooses |
| 19 | mMERQ-PD | PI chooses |
| 20 | SCOPA-AUT | PI chooses |
| 21 | RBD Screening Questionnaire | PI chooses |
| 22 | RBD single question | PI chooses |
| 23 | PSG RBD (performed, yes/no) | PI chooses |
| 24 | Depression | PI chooses — name the scale in the note |
| 25 | Epworth Sleepiness Scale | PI chooses |
| 26 | Smell testing | PI chooses — name the test in the note |
| 27 | Pure autonomic failure - clinical diagnosis | PI chooses |
| 28 | QUIP | PI chooses — RS or CS, in the note |
| 29 | PDQ-8/39 | PI chooses — which version, in the note |
| 30 | PSP-RS | PI chooses |
| 31 | UMSARS | PI chooses |
| 32 | CBFS A | PI chooses |

MDS-UPDRS parts are listed separately because cohorts often hold some parts and not others — Part 4 in particular.

## 8. Storage schema

One row per `phenotype × item × period`. Store long, present wide.

```
cohort_id, contact_name, contact_email, study_status,
phenotype, item_class, item, design, period, deadline,
n_new, n_followup, n_total, interval, note
```

- `item_class` ∈ {`sample`, `clinical`}
- `design` ∈ {`Cross-sectional`, `Longitudinal`}
- `period` ∈ {`baseline`, `2027`, `2028`, …}

The `period` column is what carries the year projection, so adding a year, a domain or a phenotype never changes the schema. Any wide table leadership wants is a pivot.

## 9. Validation

**Hard (blocks submission)**
- `cohort_id` present
- `contact_email` present and contains `@`
- At least one non-zero number
- DNA numbers entered
- Valid deadline

**Soft (warns, does not block)**
- An item's planned participants exceed that phenotype's DNA total → likely a clinical-only or autopsy subset, or an error. Warn, never block.
- A domain marked longitudinal with no follow-up numbers anywhere
- Follow-up numbers entered with no repeat interval
- Ongoing study whose plan covers no years
- Deadline in the past

Negative numbers are prevented at the widget rather than validated afterwards.

## 10. Open decisions

For us:

1. **Pre-fill and optimism.** Both screens now seed from DNA. Blood usually is close to the genotyped count; CSF and brain rarely are. Watch the first few real submissions for CSF numbers left at the DNA figure — if that happens, seed only blood, or seed nothing on screen 4.
2. **Follow-up unit.** `n_followup` counts *participants contributing a repeat in that year*, not observations. For progression modelling the number of visits per person matters, and the repeat interval field only partly covers it. Adding an expected-visits column later means re-collecting.
3. **Domains needing an instrument named** — Depression, Smell testing, QUIP, PDQ-8/39 are handled with free text in the note column. If we want these analysable without cleanup, they need controlled options instead.
4. **Verify before this reaches PIs**: "CBFS A" (is the A a subscale?), "MERQ-PD" vs "mMERQ-PD", and whether "PSG RBD" should capture a count or only yes/no. The original list wrote MDS-UPRDS; read as MDS-UPDRS throughout.
5. **Matrix size.** The matrix renders one control per item × phenotype — 32 domains across 5 arms is 160 controls, and each click reruns the script. Fine at the sizes tested; if a cohort selects everything for many phenotypes it may feel slow. Worth watching before assuming it scales.
6. **Year cap.** The prototype stops at 10 projected years. Longer studies get truncated silently — decide whether to hard-cap or roll the tail into a single "beyond" column.

For Lietsel and whoever builds it:

7. **Authentication.** REDCap is not available to GP2, and PIs will not create accounts. Plan on per-cohort tokenised links.
8. **Save and resume** is non-negotiable. No PI completes this in one sitting.
9. **Persistence** — Sheets, BigQuery, or Firestore behind the app. The app is a UI over a table, not a store.
10. **Ownership.** Whoever builds this maintains it for the life of the consortium. Worth naming a person now.

## 11. Prototype

`transfer_plan_app.py` implements everything above except authentication and persistence. Run it, click **Load an example cohort**, and step through the sidebar. The last sidebar item is the GP2 tracking view — the "who is lagging" screen, which no form produces at all.
