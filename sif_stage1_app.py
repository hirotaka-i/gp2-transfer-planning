"""
GP2 Site Interest Form — Stage 1 prototype

Replaces the Google Form. A cohort fills this once, before any agreement is in
place, to tell GP2 what exists and roughly how much. The answers seed Stage 2
(the transfer plan / SOW), which asks for firm numbers at instrument level.

Vocabulary is loaded from CSV so it can be edited without touching this file:
  vocab/gp2_L1_constructs.csv   34 constructs, the domain matrix
  vocab/gp2_biosamples.csv      biosample list
  vocab/gp2_omics.csv           assay x tissue combinations

Run:  streamlit run sif_stage1_app.py
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import report

st.set_page_config(page_title="GP2 Site Interest Form", layout="wide")

VOCAB = Path(__file__).parent / "vocab"

CROSS_SECTIONAL, LONGITUDINAL, NOT_COLLECTED = "Cross-sectional", "Longitudinal", "None"
SHORT = {CROSS_SECTIONAL: "CS", LONGITUDINAL: "LT", None: NOT_COLLECTED}
LONG_LABEL = {"CS": CROSS_SECTIONAL, "LT": LONGITUDINAL, NOT_COLLECTED: None}

PHENOTYPES = [
    "PD", "Control", "PSP", "DLB", "MSA", "CBD/CBS", "FTD", "AD", "Mix",
    "VaD", "VaPD", "Population Control", "Undetermined-MCI",
    "Undetermined-Dementia", "Prodromal", "LBD", "Other",
]
CASE_PHENOTYPES = [p for p in PHENOTYPES
                   if p not in ("Control", "Population Control")]

# Diagnostic criteria differ by phenotype. The single PD-only list in the
# Google Form cannot be answered correctly by a PSP or MSA cohort.
DX_CRITERIA = {
    "PD": ["MDS clinical diagnostic criteria", "UK Brain Bank criteria"],
    "PSP": ["MDS-PSP (Höglinger 2017)", "NINDS-SPSP (Litvan 1996)"],
    "MSA": ["MDS-MSA (2022)", "Gilman 2008"],
    "DLB": ["McKeith 2017"], "LBD": ["McKeith 2017"],
    "CBD/CBS": ["Armstrong 2013"],
    "FTD": ["Rascovsky 2011 (bvFTD)", "Gorno-Tempini 2011 (PPA)"],
    "AD": ["NIA-AA", "NINCDS-ADRDA"],
    "VaD": ["NINDS-AIREN"], "VaPD": ["NINDS-AIREN"],
    "Prodromal": ["MDS research criteria for prodromal PD", "PREDICT-PD"],
}

PRODROMAL_FEATURES = [
    "RBD - PSG confirmed", "RBD - interview suspected", "RBD - questionnaire only",
    "Hyposmia/anosmia - smell clinic confirmed", "Hyposmia/anosmia - objectively tested",
    "Hyposmia/anosmia - self-reported", "At risk by MDS prodromal criteria",
    "At risk by PREDICT-PD", "At risk by polygenic risk score",
    "Non-manifesting carrier - GBA", "Non-manifesting carrier - LRRK2",
    "Non-manifesting carrier - PRKN/PINK1/DJ1", "Non-manifesting carrier - SNCA",
    "Non-manifesting carrier - other",
]
CASE_CATEGORIES = ["Early-onset (AAO < 50)", "Late-onset", "Familial (2+ affected)",
                   "Non-familial", "Movement-disorder-associated mutation carriers"]
TIMESPANS = ["Cross-sectional", "Cross-sectional plus", "Longitudinal (prospective)",
             "Longitudinal (retrospective)"]
SETTINGS = ["Population sample", "Hospital", "Primary care", "Other"]
CONTEXTS = ["Observational study", "Interventional study (e.g. drug trial)"]
REGIONS = ["North America", "South America", "Europe", "Africa", "Asia/Oceania",
           "Multi-region"]
DNA_SOURCES = ["Blood", "Saliva", "Brain", "Other"]
# Which biosample must be on the list for each answer, so the source of the DNA
# is actually being transferred.
DNA_SOURCE_SAMPLE = {"Blood": "blood", "Saliva": "saliva",
                     "Brain": "brain (post-mortem)"}
YESNO = ["Yes", "No", "Not sure"]

# Timespan seeds the domain matrix. Cross-sectional plus is one assessment with
# follow-up questionnaires / EPR / mortality tracking, which is exactly these two.
ALWAYS_LT_IN_CS_PLUS = {"Mortality / vital status", "Disease course / complications"}


REQUIRED_L1_COLS = ["category", "l1", "type", "default_on", "phenotype_scope",
                    "fixed_design", "in_dictionary", "examples"]


def load_vocab():
    """Read the vocabulary CSVs on every run.

    Deliberately NOT cached. These files exist to be edited by whoever owns the
    vocabulary, and a cache means an edit silently does nothing until the server
    is restarted — which looks exactly like the feature being broken. They are a
    few hundred rows; re-reading costs nothing.
    """
    l1 = pd.read_csv(VOCAB / "gp2_L1_constructs.csv")
    missing = [c for c in REQUIRED_L1_COLS if c not in l1.columns]
    if missing:
        st.error(f"`vocab/gp2_L1_constructs.csv` is missing these columns: "
                 f"{', '.join(missing)}. It is probably an older copy — replace it "
                 f"with the current file. Defaults are being applied instead, so "
                 f"every domain will look switched on.")
        for c in missing:
            l1[c] = {"default_on": 1, "fixed_design": "", "in_dictionary": True,
                     "examples": "", "phenotype_scope": "all", "category": "Other",
                     "type": "construct"}.get(c, "")
    bios = pd.read_csv(VOCAB / "gp2_biosamples.csv")
    omics = pd.read_csv(VOCAB / "gp2_omics.csv")
    return l1, bios, omics


# --------------------------------------------------------------------------
# State. Same two Streamlit traps as the Stage 2 app; see CLAUDE.md.
#   1. A widget's output is never fed back as its own value=/default=.
#   2. Keyed widget state is discarded when not rendered, so plain widgets are
#      re-assigned each run and editors rebuild on navigation via _nav.
# --------------------------------------------------------------------------

TEXT_KEYS = {
    "w_contact_name": "", "w_contact_email": "", "w_institution": "",
    "w_study_short": "", "w_study_full": "", "w_pi_name": "", "w_pi_email": "",
    "w_country": "", "w_doi": "", "w_setting_other": "", "w_dna_source_other": "",
    "w_ethics_board": "", "w_recruit_features": "", "w_free_note": "",
    "w_other_phenotype": "", "w_other_domains": "", "w_other_biosample": "",
}
CHOICE_KEYS = {
    "w_timespan": TIMESPANS[0], "w_setting": SETTINGS[0], "w_context": CONTEXTS[0],
    "w_region": REGIONS[0], "w_multisite": "No", "w_dna_local": "Yes",
    "w_dna_source": DNA_SOURCES[0], "w_recontact": "Yes", "w_analytic": "Not sure",
    "w_redcap": "Not sure",
}
NUM_KEYS = {"w_year_start": 2010, "w_year_end": date.today().year + 3,
            "w_pct_monogenic": 0, "w_anc_eur": 0, "w_anc_afr": 0, "w_anc_asn": 0,
            "w_anc_hisp": 0}
LIST_KEYS = ["w_phenotypes", "w_case_categories", "w_prodromal_features",
             "w_biosamples", "w_omics", "w_followup"]
DATE_KEYS = {"w_ethics_date": date.today()}

WIDGET_KEYS = (list(TEXT_KEYS) + list(CHOICE_KEYS) + list(NUM_KEYS)
               + LIST_KEYS + list(DATE_KEYS))


def init_state():
    for d in (TEXT_KEYS, CHOICE_KEYS, NUM_KEYS, DATE_KEYS):
        for k, v in d.items():
            st.session_state.setdefault(k, v)
    for k in LIST_KEYS:
        st.session_state.setdefault(k, [])
    st.session_state.setdefault("designs", {})        # l1 -> {phenotype: design|None}
    st.session_state.setdefault("counts", None)       # DataFrame
    st.session_state.setdefault("criteria", {})       # phenotype -> dict
    st.session_state.setdefault("_editor_sigs", {})
    st.session_state.setdefault("_editor_srcs", {})
    st.session_state.setdefault("_editor_versions", {})
    st.session_state.setdefault("_nav", 0)
    st.session_state.setdefault("_last_step", None)
    st.session_state.setdefault("_seeded_timespan", None)


def persist_widget_state():
    for k in WIDGET_KEYS:
        if k in st.session_state:
            st.session_state[k] = st.session_state[k]


def phenos() -> list[str]:
    return list(st.session_state["w_phenotypes"])


def case_phenos() -> list[str]:
    return [p for p in phenos() if p in CASE_PHENOTYPES]


def editor_key(name: str) -> str:
    return f"{name}__{st.session_state['_editor_versions'].get(name, 0)}"


def editor_source(name: str, sig, build) -> pd.DataFrame:
    sig = (sig, st.session_state["_nav"])
    sigs, srcs = st.session_state["_editor_sigs"], st.session_state["_editor_srcs"]
    vers = st.session_state["_editor_versions"]
    if sigs.get(name) != sig:
        srcs[name] = build()
        sigs[name] = sig
        vers[name] = vers.get(name, 0) + 1
    return srcs[name]


def carry_over(old, new, keys):
    if old is None or old.empty:
        return new
    shared = [c for c in new.columns if c in old.columns and c not in keys]
    if not shared or not all(k in old.columns for k in keys):
        return new
    m = new.merge(old[keys + shared], on=keys, how="left", suffixes=("", "_old"))
    for c in shared:
        oc = f"{c}_old"
        if oc in m.columns:
            m[c] = m[oc].where(m[oc].notna(), m[c])
            m = m.drop(columns=[oc])
    return m[new.columns]


def fixed_design_of(row) -> str:
    """Domains collected once per person however long the study runs.
    Empty CSV cells arrive as NaN, which is truthy — hence the isna check."""
    v = row.get("fixed_design")
    return "" if v is None or pd.isna(v) else str(v).strip()


def seed_design(l1_row) -> str | None:
    """Starting value for a domain, from the declared study timespan."""
    fixed = fixed_design_of(l1_row)
    if fixed:
        return fixed
    ts = st.session_state["w_timespan"]
    if ts.startswith("Longitudinal"):
        return LONGITUDINAL
    if ts == "Cross-sectional plus" and l1_row["l1"] in ALWAYS_LT_IN_CS_PLUS:
        return LONGITUDINAL
    return CROSS_SECTIONAL


def design_of(l1: str, phenotype: str, l1_df) -> str | None:
    cell = st.session_state["designs"].get(l1, {})
    if phenotype in cell:
        return cell[phenotype]
    row = l1_df[l1_df.l1 == l1].iloc[0]
    if row["phenotype_scope"] == "case" and phenotype not in CASE_PHENOTYPES:
        return None
    if row["phenotype_scope"] == "atypical" and phenotype in ("PD", "Control",
                                                             "Population Control"):
        return None
    return seed_design(row)


# --------------------------------------------------------------------------
# Screens
# --------------------------------------------------------------------------

def screen_study():
    st.header("1. Study and contact")
    st.caption("One form per study. If you contribute samples from several studies "
               "running under separate ethics, please submit one form for each.")
    c1, c2, c3 = st.columns(3)
    c1.text_input("Contact name", key="w_contact_name")
    c2.text_input("Contact email", key="w_contact_email",
                  placeholder="name@institution.edu")
    c3.text_input("Institution", key="w_institution")

    c1, c2 = st.columns(2)
    c1.text_input("Short name of study (code/abbreviation)", key="w_study_short")
    c2.text_input("Full name of study", key="w_study_full")
    c1, c2 = st.columns(2)
    c1.text_input("Lead study PI", key="w_pi_name")
    c2.text_input("PI email", key="w_pi_email")

    c1, c2, c3 = st.columns(3)
    c1.number_input("Year study started", 1950, date.today().year, key="w_year_start")
    c2.number_input("Year completed (or estimated completion)", 1950,
                    date.today().year + 30, key="w_year_end")
    c3.radio("Multi-site study?", ["Yes", "No"], key="w_multisite", horizontal=True)

    c1, c2 = st.columns(2)
    c1.selectbox("Main recruitment setting", SETTINGS, key="w_setting")
    if st.session_state["w_setting"] == "Other":
        c1.text_input("Please specify", key="w_setting_other")
    c2.selectbox("Study context", CONTEXTS, key="w_context")

    c1, c2, c3 = st.columns(3)
    c1.selectbox("Main site region", REGIONS, key="w_region")
    c2.text_input("Country of main site", key="w_country")
    c3.text_input("Publication DOI or study webpage", key="w_doi")

    st.divider()
    st.selectbox("Study timespan", TIMESPANS, key="w_timespan",
                 help="This seeds the domain matrix on screen 3 — you can change "
                      "any cell there.")
    if st.session_state["w_timespan"].startswith("Longitudinal"):
        st.multiselect("Planned follow-up duration and visit intervals",
                       ["Every 6 months", "Annually", "Every 2 years", "Irregular"],
                       key="w_followup")

    ts = st.session_state["w_timespan"]
    if ts == "Cross-sectional":
        st.info("Every domain on screen 3 will start at **CS**.")
    elif ts == "Cross-sectional plus":
        st.info("Domains start at **CS**, except mortality / vital status and "
                "disease course, which start at **LT** — that is what makes a "
                "study cross-sectional *plus*.")
    else:
        st.info("Every domain on screen 3 will start at **LT**.")


def screen_participants():
    st.header("2. Participants")
    st.multiselect("Which phenotypes are in this study?", PHENOTYPES,
                   key="w_phenotypes")
    if "Other" in phenos():
        st.text_input("Other — please specify the diagnoses", key="w_other_phenotype",
                      placeholder="e.g. PSP-like syndrome, NPH, drug-induced parkinsonism")
    if not phenos():
        st.warning("Select at least one phenotype to continue.")
        return

    if "PD" in phenos():
        st.subheader("PD case categories")
        st.caption("Within GP2: early onset is AAO < 50; familial is 2+ individuals "
                   "with a movement disorder in the same family.")
        st.multiselect("Case categories (select all that apply)", CASE_CATEGORIES,
                       key="w_case_categories")
        st.number_input("Estimated % of cases potentially monogenic "
                        "(early onset < 50, or familial)", 0, 100,
                        key="w_pct_monogenic")

    if "Prodromal" in phenos():
        st.subheader("Prodromal")
        st.multiselect("Prodromal features and method of evaluation",
                       PRODROMAL_FEATURES, key="w_prodromal_features")

    st.subheader("Ancestry")
    st.caption("Rough breakdown among those with blood/DNA samples, at study level.")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.number_input("European %", 0, 100, key="w_anc_eur")
    c2.number_input("African %", 0, 100, key="w_anc_afr")
    c3.number_input("Asian %", 0, 100, key="w_anc_asn")
    c4.number_input("Hispanic or Latino %", 0, 100, key="w_anc_hisp")
    other = 100 - sum(st.session_state[k] for k in
                      ["w_anc_eur", "w_anc_afr", "w_anc_asn", "w_anc_hisp"])
    c5.metric("Other %", other)
    if other < 0:
        st.error("The percentages add up to more than 100.")

    st.subheader("Inclusion and exclusion criteria")
    st.caption("Asked per phenotype — diagnostic criteria differ between them.")
    for p in phenos():
        with st.expander(p, expanded=(p == phenos()[0])):
            crit = st.session_state["criteria"].setdefault(p, {})
            if p in CASE_PHENOTYPES:
                opts = DX_CRITERIA.get(p, []) + ["Other"]
                crit["dx_criteria"] = st.selectbox(
                    "Criteria used to confirm the diagnosis", opts,
                    key=f"crit_dx::{p}",
                    index=opts.index(crit["dx_criteria"]) if crit.get("dx_criteria")
                    in opts else 0)
                if crit["dx_criteria"] == "Other":
                    crit["dx_other"] = st.text_input(
                        "Please specify", crit.get("dx_other", ""),
                        key=f"crit_dxo::{p}")
                crit["stage"] = st.text_input(
                    "Disease stage criteria for recruitment",
                    crit.get("stage", ""), key=f"crit_stage::{p}",
                    placeholder="e.g. diagnosis < 5 years, H&Y < 3, drug naive")
            crit["inclusion"] = st.text_area(
                "Other inclusion criteria", crit.get("inclusion", ""),
                key=f"crit_in::{p}", height=70)
            crit["exclusion"] = st.text_area(
                "Exclusion criteria", crit.get("exclusion", ""),
                key=f"crit_ex::{p}", height=70,
                placeholder="e.g. MMSE < 27, secondary parkinsonism")

    st.text_area("Any other specific recruitment features?",
                 key="w_recruit_features", height=70)


def screen_domains():
    st.header("3. Clinical & biomarker data")
    l1_df, _, _ = load_vocab()
    if not phenos():
        st.warning("Select phenotypes on screen 2 first.")
        return
    st.caption(f"Tick a domain to say you collect it, then set it per group: "
               f"**CS** cross-sectional, once per person · **LT** longitudinal, "
               f"repeated over time · **{NOT_COLLECTED}** not collected in that "
               f"group. Untick the whole row if you do not collect it at all.")
    st.caption("Only the domains most cohorts hold are ticked to begin with, and "
               "CS/LT follows your study timespan. Change only what differs.")

    # Re-seeding on a timespan change is the one case where the store is
    # deliberately discarded — the PI just told us the whole study is different.
    if st.session_state["_seeded_timespan"] != st.session_state["w_timespan"]:
        st.session_state["designs"] = {}
        for k in [k for k in st.session_state
                  if str(k).startswith(("seg::", "on::"))]:
            del st.session_state[k]
        st.session_state["_seeded_timespan"] = st.session_state["w_timespan"]

    ps = phenos()
    for cat, grp in l1_df.groupby("category", sort=False):
        st.subheader(cat)
        head = st.columns([3] + [1] * len(ps))
        head[0].caption("")
        for col, p in zip(head[1:], ps):
            col.caption(f"**{p}**")

        for _, row in grp.iterrows():
            l1 = row["l1"]
            on_key = f"on::{l1}"
            if on_key not in st.session_state:
                st.session_state[on_key] = bool(row.get("default_on", 1))
            cols = st.columns([3] + [1] * len(ps))

            label = l1 + (" ⚠︎" if not row["in_dictionary"] else "")
            cols[0].checkbox(label, key=on_key)
            on = st.session_state[on_key]
            ex = row.get("examples")
            if isinstance(ex, str) and ex.strip():
                cols[0].caption(ex if on else f":gray[{ex}]")

            opts = ([NOT_COLLECTED, "CS"] if fixed_design_of(row)
                    else [NOT_COLLECTED, "CS", "LT"])
            for col, p in zip(cols[1:], ps):
                key = f"seg::{l1}::{p}"
                if key not in st.session_state:
                    st.session_state[key] = SHORT[design_of(l1, p, l1_df)]
                if st.session_state[key] not in opts:
                    st.session_state[key] = "CS"
                col.segmented_control(f"{l1} · {p}", opts, key=key,
                                      label_visibility="collapsed", disabled=not on)
                # Unticking the row is the same answer as setting every cell to
                # None, but it takes one click instead of one per phenotype.
                st.session_state["designs"].setdefault(l1, {})[p] = (
                    LONG_LABEL.get(st.session_state[key] or NOT_COLLECTED)
                    if on else None)

    st.caption("⚠︎ = no GP2 data dictionary schema yet. We still want to know it "
               "exists, but it cannot be scheduled for transfer until the "
               "dictionary covers it.")
    st.text_area("Anything else you collect that is not listed above?",
                 key="w_other_domains", height=70,
                 help="Free text. These become candidates for the GP2 data "
                      "dictionary.")


def screen_samples():
    st.header("4. Samples and numbers")
    _, bios, omics = load_vocab()
    if not phenos():
        st.warning("Select phenotypes on screen 2 first.")
        return

    c1, c2 = st.columns(2)
    c1.radio("Is extracted DNA available now?", ["Yes", "No"],
             key="w_dna_local", horizontal=True,
             help="Yes if you hold extracted DNA. No if GP2 would extract it "
                  "from material you send.")
    c2.selectbox("Source of DNA", DNA_SOURCES, key="w_dna_source")
    if st.session_state["w_dna_source"] == "Other":
        c2.text_input("Please specify", key="w_dna_source_other")

    have_dna = st.session_state["w_dna_local"] == "Yes"
    src = st.session_state["w_dna_source"]
    src_sample = DNA_SOURCE_SAMPLE.get(src)
    if have_dna:
        st.caption("Because you hold extracted DNA, the **DNA** row below is what "
                   "GP2 counts as the cohort size.")
    else:
        label = src_sample or (st.session_state["w_dna_source_other"] or "the source material")
        st.caption(f"Because DNA will be extracted after transfer, the **{label}** "
                   f"row below is what GP2 counts as the cohort size.")

    st.multiselect("Which biosamples do you have, or plan to collect?",
                   bios.biosample.tolist(), key="w_biosamples")
    if "Other" in st.session_state["w_biosamples"]:
        st.text_input("Other biosample — please specify", key="w_other_biosample")
    st.multiselect("Omics data available", omics.label.tolist(), key="w_omics")

    chosen = list(st.session_state["w_biosamples"])
    if not chosen:
        st.info("Select at least one biosample to give numbers.")
        st.session_state["counts"] = None
        return

    horizon = int(st.session_state["w_year_end"])
    st.subheader("Numbers")
    st.caption(f"Participants, not tubes. **Now** is what exists today; "
               f"**by {horizon}** is the total you expect by the end of your "
               f"study. Estimates are fine — Stage 2 asks for firm numbers.")
    rows = [{"Phenotype": p, "Sample": s} for p in phenos() for s in chosen]
    key_cols = ["Phenotype", "Sample"]
    vcols = ["Now", f"By {horizon}"]

    def build():
        new = pd.DataFrame([{**r, **{c: 0 for c in vcols}, "Note": ""} for r in rows])
        return carry_over(st.session_state["counts"], new, key_cols)

    src = editor_source("counts", (tuple(map(tuple, [r.values() for r in
                                                     [dict(r) for r in rows]])),
                                   tuple(vcols)), build)
    cfg = {c: st.column_config.TextColumn(disabled=True) for c in key_cols}
    for c in vcols:
        cfg[c] = st.column_config.NumberColumn(min_value=0, step=1, format="%d")
    cfg["Note"] = st.column_config.TextColumn()
    st.session_state["counts"] = st.data_editor(
        src, hide_index=True, width="stretch", key=editor_key("counts"),
        column_config=cfg)

    bad = st.session_state["counts"]
    over = bad[bad["Now"] > bad[f"By {horizon}"]]
    if not over.empty:
        st.error(f"{len(over)} rows have a current number larger than the "
                 f"{horizon} projection. The projection is a **total**, not an "
                 f"increment, so it can never be smaller than what exists today.")
        st.dataframe(over[["Phenotype", "Sample", "Now", f"By {horizon}"]],
                     hide_index=True, width="stretch")


def screen_ethics():
    st.header("5. Ethics and additional questions")
    st.caption("Before final inclusion in GP2, a committee reviews your consent "
               "form to confirm samples and data can be shared broadly. If it was "
               "already approved through the Monogenic Network it need not be "
               "reviewed again.")
    c1, c2 = st.columns(2)
    c1.text_input("Which ethics committee approved this research?",
                  key="w_ethics_board")
    c2.date_input("Date of ethics board approval", key="w_ethics_date")

    st.radio("Can participants be recontacted for further follow-up or research?",
             ["Yes", "No"], key="w_recontact", horizontal=True)
    st.radio("Would you like analytical support from the GP2 data analysis team?",
             YESNO, key="w_analytic", horizontal=True)
    st.radio("Interested in using the GP2 REDCap database for de-identified "
             "clinical data? (optional, under development)", YESNO,
             key="w_redcap", horizontal=True)
    st.text_area("Free note — any other data types you can provide",
                 key="w_free_note", height=90)


# --------------------------------------------------------------------------
# Export — this is what Stage 2 consumes
# --------------------------------------------------------------------------

def to_long() -> pd.DataFrame:
    l1_df, _, _ = load_vocab()
    rows = []
    for _, r in l1_df.iterrows():
        for p in phenos():
            d = st.session_state["designs"].get(r["l1"], {}).get(p)
            if d is None:
                continue
            rows.append({"phenotype": p, "kind": "domain", "item": r["l1"],
                         "category": r["category"], "design": d,
                         "in_dictionary": bool(r["in_dictionary"])})
    counts = st.session_state.get("counts")
    if counts is not None and not counts.empty:
        horizon = f"By {int(st.session_state['w_year_end'])}"
        for _, r in counts.iterrows():
            rows.append({"phenotype": r["Phenotype"], "kind": "biosample",
                         "item": r["Sample"], "category": "Biosample",
                         "design": "", "in_dictionary": True,
                         "n_now": int(r["Now"]), "n_horizon": int(r[horizon]),
                         "note": r.get("Note", "")})
    return pd.DataFrame(rows)


def snapshot() -> dict:
    return {
        "stage": 1,
        "submitted": date.today().isoformat(),
        "study": {k: (str(st.session_state[k]) if k in DATE_KEYS
                      else st.session_state[k]) for k in WIDGET_KEYS},
        "criteria": st.session_state["criteria"],
        "designs": {l1: {p: d for p, d in cell.items()}
                    for l1, cell in st.session_state["designs"].items()},
        "plan": to_long().to_dict("records"),
    }


def validate() -> tuple[list[str], list[str]]:
    e, w = [], []
    if not st.session_state["w_study_short"].strip():
        e.append("Short study name is required.")
    if "@" not in st.session_state["w_contact_email"]:
        e.append("A contact email is required.")
    if not phenos():
        e.append("Select at least one phenotype.")
    anc = sum(st.session_state[k] for k in
              ["w_anc_eur", "w_anc_afr", "w_anc_asn", "w_anc_hisp"])
    if anc > 100:
        e.append("Ancestry percentages add up to more than 100.")
    elif anc == 0 and phenos():
        w.append("No ancestry breakdown given.")
    if "Other" in phenos() and not st.session_state["w_other_phenotype"].strip():
        w.append("'Other' phenotype selected but not specified.")
    have_dna = st.session_state["w_dna_local"] == "Yes"
    chosen = set(st.session_state["w_biosamples"])
    src = st.session_state["w_dna_source"]
    src_sample = DNA_SOURCE_SAMPLE.get(src)
    if have_dna and "DNA" not in chosen:
        e.append("You said extracted DNA is available, but DNA is not in the "
                 "biosample list. Either tick DNA or change that answer.")
    if not have_dna:
        if src == "Other" and not st.session_state["w_dna_source_other"].strip():
            e.append("DNA source is 'Other' but has not been specified.")
        elif src_sample and src_sample not in chosen:
            e.append(f"DNA will be extracted from {src.lower()}, but "
                     f"'{src_sample}' is not in the biosample list. GP2 cannot "
                     f"extract from material that is not being transferred.")

    counts = st.session_state.get("counts")
    if counts is None or counts.empty or counts[["Now"]].sum().sum() == 0:
        w.append("No sample numbers entered yet.")
    else:
        horizon = f"By {int(st.session_state['w_year_end'])}"
        if horizon in counts.columns:
            bad = counts[counts["Now"] > counts[horizon]]
            for _, r in bad.iterrows():
                e.append(f"{r['Phenotype']} / {r['Sample']}: {horizon} is "
                         f"{int(r[horizon])} but {int(r['Now'])} already exist. "
                         f"The projection is a total, not an increment.")
    long = to_long()
    dom = long[long.kind == "domain"] if not long.empty else long
    if not dom.empty:
        no_schema = dom[~dom.in_dictionary]["item"].unique()
        if len(no_schema):
            w.append("Collected but not yet in the GP2 data dictionary: "
                     + ", ".join(sorted(no_schema))
                     + ". Recorded, but not transferable until the dictionary covers it.")
    return e, w


def build_pdf(long: pd.DataFrame) -> bytes:
    """Screens 1-5 as a document the cohort can sign off and GP2 can file."""
    m = st.session_state
    horizon = int(m["w_year_end"])
    src = m["w_dna_source"]
    if src == "Other" and m["w_dna_source_other"].strip():
        src = f"Other — {m['w_dna_source_other']}"
    sections = [
        ("1. Study and contact", [report.fields([
            ("Contact", f"{m['w_contact_name']} · {m['w_contact_email']}"),
            ("Institution", m["w_institution"]),
            ("Study", f"{m['w_study_short']} — {m['w_study_full']}"),
            ("Lead PI", f"{m['w_pi_name']} · {m['w_pi_email']}"),
            ("Years", f"{m['w_year_start']} to {horizon}"),
            ("Multi-site", m["w_multisite"]),
            ("Setting", m["w_setting"] + (f" ({m['w_setting_other']})"
                                          if m["w_setting"] == "Other" else "")),
            ("Context", m["w_context"]),
            ("Region / country", f"{m['w_region']} · {m['w_country']}"),
            ("Timespan", m["w_timespan"]),
            ("Follow-up", ", ".join(m["w_followup"])),
            ("Reference", m["w_doi"]),
        ])]),
        ("2. Participants", [report.fields([
            ("Phenotypes", ", ".join(phenos())),
            ("Other phenotypes", m["w_other_phenotype"]),
            ("PD case categories", ", ".join(m["w_case_categories"])),
            ("Potentially monogenic", f"{m['w_pct_monogenic']}%"),
            ("Prodromal features", ", ".join(m["w_prodromal_features"])),
            ("Ancestry", f"European {m['w_anc_eur']}% · African {m['w_anc_afr']}% · "
                         f"Asian {m['w_anc_asn']}% · Hispanic/Latino "
                         f"{m['w_anc_hisp']}%"),
            ("Recruitment features", m["w_recruit_features"]),
        ])]),
    ]

    crit = []
    for p in phenos():
        c = m["criteria"].get(p, {})
        if not any(str(v).strip() for v in c.values()):
            continue
        crit.append({"Phenotype": p,
                     "Diagnostic criteria": c.get("dx_criteria", ""),
                     "Stage criteria": c.get("stage", ""),
                     "Inclusion": c.get("inclusion", ""),
                     "Exclusion": c.get("exclusion", "")})
    if crit:
        sections.append(("Inclusion and exclusion criteria",
                         report.frame(pd.DataFrame(crit),
                                      widths=[14, 22, 20, 22, 22])))

    dom = long[long.kind == "domain"] if not long.empty else pd.DataFrame()
    if not dom.empty:
        wide = (dom.pivot_table(index="item", columns="phenotype", values="design",
                                aggfunc="first").fillna(NOT_COLLECTED)
                .replace({CROSS_SECTIONAL: "CS", LONGITUDINAL: "LT"})
                .reset_index().rename(columns={"item": "Domain"}))
        sections.append(("3. Clinical and biomarker data", report.frame(wide)))

    bio = long[long.kind == "biosample"] if not long.empty else pd.DataFrame()
    samples = [report.fields([
        ("Extracted DNA available", m["w_dna_local"]),
        ("Source of DNA", src),
        ("Biosamples", ", ".join(m["w_biosamples"])),
        ("Other biosample", m["w_other_biosample"]),
        ("Omics", ", ".join(m["w_omics"])),
    ])]
    if not bio.empty:
        tab = (bio[["phenotype", "item", "n_now", "n_horizon", "note"]]
               .rename(columns={"phenotype": "Phenotype", "item": "Sample",
                                "n_now": "Now", "n_horizon": f"By {horizon}",
                                "note": "Note"}))
        samples += report.frame(tab)
    sections.append(("4. Samples and numbers", samples))

    sections.append(("5. Ethics and other", [report.fields([
        ("Ethics committee", m["w_ethics_board"]),
        ("Approval date", m["w_ethics_date"]),
        ("Recontact possible", m["w_recontact"]),
        ("Analytical support requested", m["w_analytic"]),
        ("Interested in GP2 REDCap", m["w_redcap"]),
        ("Free note", m["w_free_note"]),
        ("Other domains collected", m["w_other_domains"]),
    ])]))
    return report.build("GP2 Site Interest Form",
                        report.stamp(m["w_study_short"]), sections)


def screen_review():
    st.header("6. Review and submit")
    errors, warnings = validate()
    for x in errors:
        st.error(x)
    for x in warnings:
        st.warning(x)

    long = to_long()
    if long.empty:
        return
    dom = long[long.kind == "domain"]
    bio = long[long.kind == "biosample"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Phenotypes", len(phenos()))
    c2.metric("Domains collected", dom["item"].nunique())
    c3.metric("Longitudinal domains",
              dom[dom.design == LONGITUDINAL]["item"].nunique())

    if not dom.empty:
        st.subheader("Domain matrix")
        st.dataframe(dom.pivot_table(index="item", columns="phenotype",
                                     values="design", aggfunc="first")
                     .fillna(NOT_COLLECTED), width="stretch")
    if not bio.empty:
        st.subheader("Sample numbers")
        st.dataframe(bio.pivot_table(index="item", columns="phenotype",
                                     values="n_now", aggfunc="sum", fill_value=0),
                     width="stretch")

    st.subheader("What gets stored")
    st.dataframe(long, hide_index=True, width="stretch")

    name = st.session_state["w_study_short"] or "draft"
    c1, c2, c3 = st.columns(3)
    c1.download_button("Download for Stage 2 (JSON)",
                       json.dumps(snapshot(), indent=2, default=str),
                       file_name=f"sif_{name}.json", mime="application/json",
                       type="primary")
    c2.download_button("Download summary (CSV)", long.to_csv(index=False),
                       file_name=f"sif_{name}.csv", mime="text/csv")
    c3.download_button("Download report (PDF)", build_pdf(long),
                       file_name=f"sif_{name}.pdf", mime="application/pdf")
    st.caption("The JSON is what the transfer-plan app reads when the DTA/MTA is "
               "drawn up: it pre-selects the instruments matching these domains "
               "and carries the numbers over as a starting point. In production "
               "this hand-off is a database record, not a file.")


# --------------------------------------------------------------------------
# Shell
# --------------------------------------------------------------------------

STEPS = {
    "1. Study & contact": screen_study,
    "2. Participants": screen_participants,
    "3. Clinical & biomarker data": screen_domains,
    "4. Samples & numbers": screen_samples,
    "5. Ethics & other": screen_ethics,
    "6. Review & submit": screen_review,
}


def load_demo():
    st.session_state.update({
        "w_contact_name": "A. Example", "w_contact_email": "a.example@institution.edu",
        "w_institution": "Example University", "w_study_short": "DEMO",
        "w_study_full": "Demonstration Parkinson's Cohort", "w_pi_name": "B. Example",
        "w_pi_email": "b.example@institution.edu", "w_year_start": 2015,
        "w_year_end": date.today().year + 2, "w_timespan": TIMESPANS[2],
        "w_region": "Europe", "w_country": "Luxembourg",
        "w_phenotypes": ["PD", "Control", "Prodromal"],
        "w_case_categories": ["Late-onset", "Non-familial"], "w_pct_monogenic": 8,
        "w_anc_eur": 85, "w_anc_afr": 2, "w_anc_asn": 5, "w_anc_hisp": 3,
        "w_biosamples": ["DNA", "blood", "plasma", "CSF"],
        "w_omics": ["RNAseq — blood"],
    })
    st.session_state["designs"] = {}
    st.session_state["counts"] = None
    st.session_state["criteria"] = {}
    st.session_state["_seeded_timespan"] = None
    for k in [k for k in st.session_state if str(k).startswith(("seg::", "on::"))]:
        del st.session_state[k]
    st.session_state["_editor_sigs"] = {}
    st.session_state["_editor_srcs"] = {}


def sidebar():
    st.sidebar.title("GP2 Site Interest Form")
    st.sidebar.caption("Stage 1 prototype — not a live collection.")
    step = st.sidebar.radio("Step", list(STEPS), label_visibility="collapsed")
    st.sidebar.divider()
    if st.sidebar.button("Load an example cohort"):
        load_demo()
        st.rerun()
    st.sidebar.divider()
    l1_df, bios, _ = load_vocab()
    st.sidebar.caption(f"Vocabulary: {len(l1_df)} domains "
                       f"({int(l1_df.default_on.sum())} ticked by default), "
                       f"{len(bios)} biosamples.")
    st.sidebar.divider()
    st.sidebar.caption("Stage 1 tells GP2 what exists, at domain level, to decide "
                       "genotyping vs sequencing. Stage 2 (the transfer plan app) "
                       "turns it into a schedule at instrument level once the "
                       "DTA/MTA is drawn up.")
    return step


def main():
    init_state()
    persist_widget_state()
    step = sidebar()
    if st.session_state["_last_step"] != step:
        st.session_state["_nav"] += 1
        st.session_state["_last_step"] = step
    STEPS[step]()


if __name__ == "__main__":
    main()
