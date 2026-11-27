# Limitations and what would come next

## Limitations of this capstone build

- The reasoning layer is a deterministic stand-in. Intent comes from configured phrases, not from a language model. Paraphrases outside those phrases become `UNCLEAR` and escalate. That is safe and it is also narrow.
- The synthetic evaluation scores that stand-in. High decision accuracy is evidence that the harness is consistent with its labels. It is not a benchmark of a production model, and it is not a business result.
- Risk scores in the demo and tests are stored fixtures. A missing or stale score fails closed to the highest band. There is no trained model in this repository.
- Nothing is delivered. Email and SMS are decisions, not provider calls. There is no telephony, no bank feed, and no live customer data.
- The database is SQLite. `seed_data.py` is the historical development fixture and must not be re-run casually, because several inserts are not idempotent. The class demo uses `data/demo_cleartide.db` instead.
- Human review is one queue and one disposition. It is not a ticketing system, and it does not authenticate a reviewer.
- Audit immutability is enforced on the application path. A person with direct SQL access can still change a file. The control a professor can see is that the application refuses the rewrite.
- Quiet hours, consent, frequency, and truthfulness rules are engineering controls modeled on familiar consumer-communications concerns. They are not a certification under the TCPA, the FDCPA, or any state collections statute. Thresholds in `config/policy.yaml` are marked provisional in that file.
- Debt types, plan lengths, and dollar thresholds are development values.
- The system is single-tenant and English-only.

## Future development, outside this freeze

- Put a real model behind the same intent and action schemas, and keep `validate_action` as the authority.
- Replace fixture risk with a documented, versioned score and a staleness clock tied to the proposed send time as well as “now.”
- Connect an outbound email and SMS provider only after the same policy checks, and log the provider id on the audit note.
- Give reviewers an authenticated queue.
- Move commercial integrations, telephony, and onboarding to a separate product repository so this capstone tree stays reproducible.
