# Change log

## Class-demo freeze

- Kept FR-4.5 channel selection and added critical-risk and medium-risk selector tests.
- Test fixtures that stored a September 2026 risk score now score at runtime, so FR-3.4 staleness does not silently change older graph tests.
- Added a one-disposition human review queue. The disposition is appended as an audit note and is visible to the next decision. The finalized decision row cannot be rewritten through the application.
- Added the local dashboard, the five class scenarios, the synthetic evaluation, the generated traceability matrix, and the offline backup.
- FR-6.4 is covered by proxy checks on the review brief: required sections, a plain gloss for every code, no JSON in the brief, and a Flesch-Kincaid grade at or below 8.
- Presentation polish: root README aligned with DEMO.md, audit timeline written in plain lines instead of raw JSON, and decision cleanup deletes audit notes before parent rows so a fresh database still passes.
- Added `streamlit_app.py` for Streamlit Community Cloud. It builds the demo database on startup and reuses the existing agent.
