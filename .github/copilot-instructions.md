# Copilot instructions

The working context for this repo lives in **`CLAUDE.md`** at the root, with the
model explained in **`docs/DESIGN.md`**. Read both before changing code; this
file only exists so Copilot picks the same context up.

The short version:

- Two Streamlit apps. Stage 1 collects what a cohort has; Stage 2 turns it into
  a transfer plan. Most changes are CSV edits under `vocab/`, not code.
- Run `pytest -q` before and after every change. Streamlit fails by producing a
  silently wrong value, not by crashing.
- Never feed a widget's output back in as its own `value=`, `default=`, or as
  the frame handed to `st.data_editor`.
- Widget state is discarded when a widget stops rendering. Anything the user
  decided must be re-seeded from the plain-dict store, not from its default.
- Don't cache the vocabulary CSVs — they exist to be edited.

`CLAUDE.md` explains why each of these matters and what broke when they were
ignored.
