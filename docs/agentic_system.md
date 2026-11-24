# What is agentic here, and where the policy comes from

## Agentic, not a single collections script

A conventional collections automation script is one sequence: if the invoice is 7 days late, send template A; if it is 30 days late, send template B. The allowed action and the message are the same rule.

Cleartide splits that into two roles.

1. The agent looks at the customer’s words, chooses which evidence tools to call, and recommends an action, a channel, and a draft. A delivery complaint calls `verify_invoice_delivery`. An “I already paid” claim calls `reconcile_payment_claim`. A payment-plan request calls payment history, promise history, and risk. Hostile or unclear replies call no tools and stop. That choice of tools is the agentic part: the path is not one fixed workflow.
2. The deterministic policy validator does not recommend. It authorizes. It can approve the recommendation, force one safe revision, or stop the case for a person. Scenario 3 in the demo is the proof: the recommender’s draft can contain language the policy refuses, and the message is not sent.

The orchestration is a LangGraph state machine in `src/agent.py`. State is explicit (`src/state.py`). Tool calls are guarded and stored (`src/tool_guard.py`, `tool_calls`). The development reasoning inside the nodes is a deterministic stand-in, `DETERMINISTIC_MOCK`, so the class demo and the tests do not depend on a model or an API key. Replacing that stand-in with a model later does not move authority. The model would still return the same schemas. `validate_action` would still decide.

## Where policies originate

Policies are not hidden in prompts, and they are not produced by the model.

**External parameters.** `config/policy.yaml` is the machine-readable source for bounds that should change without a code edit: policy version, confidence threshold, tool-call caps, intent precedence, risk bands and staleness, payment-plan duration and down-payment by risk band, whether a band may be offered autonomously, consumer quiet hours, the seven-day contact cap, SMS-consent and opt-out switches, the disputed-amount threshold, high-value and tenure thresholds, sensitive-language terms, truthfulness term lists, and the hard/soft split. `load_policy()` reads that file. The file header states that the numbers are provisional engineering values for the academic prototype and are not a substitute for legal review.

**Hard enforcement.** `src/policy.py` `validate_action` is ordinary Python. It does not call a model. Every proposal passes through it before an autonomous action can finish. A hard violation returns `REJECTED` or `ESCALATE` with the constraint id and the fields that triggered it (`violated_constraints`, `violated_fields`).

**Schema exclusions.** `src/schemas.py` `ActionType` has no discount, waiver, write-off, or service-hold action. The recommender cannot select an action the schema does not name.

**Account records.** Consent, opt-out, debt type, lifetime value, and customer start date come from the relational account, not from the customer’s sentence.

## What the contact and truthfulness rules are modeled on

The prototype uses patterns that collections and consumer-communications teams will recognize. It does not claim to implement a statute, and it does not cite one in code.

- **Consent and quiet hours.** Consumer SMS is refused without recorded affirmative consent, and consumer SMS inside the configured window (21:00–08:00 in the development file) is refused. Email is outside that quiet-hour rule. Opt-out of a channel is stored and blocks that channel. These are the same kinds of controls associated with TCPA-style consent and calling-hour limits. The window and the on/off switches are YAML parameters. Passing them is not a legal opinion that a live text would be TCPA-compliant.
- **Truthfulness and representation.** The validator blocks unauthorized consequence language (including “legal action,” “lawsuit,” “wage garnishment,” “arrest,” and credit-bureau threats) and blocks the agent from calling itself a third-party collector or collection agency. A stated dollar amount has to match the ledger. Those prohibitions follow the same concerns as FDCPA-style false, misleading, or threatening representations. Cleartide’s product position is first-party: the hauler speaks in its own name. The code enforces that by rejecting third-party-collector phrasing. It is not an FDCPA compliance program.
- **Authority limits that are business policy, not statute.** Payment-plan length and down payment by risk band, the disputed-amount escalation threshold, firm-tone review for high-value or long-tenure accounts, and the seven-day contact cap are operating rules for this prototype. The cap is 4 in the development file because that number is configured there, not because a statute sets it to 4.

`GV-5` is the kill switch: `agent.autonomous_action_enabled: false` forces escalation.

## How a rule actually fires

For the blocked-draft scenario the path is:

1. The customer sentence is classified.
2. The recommendation’s `message_body` is replaced, in the demo only, with “Failure to pay may result in legal action.”
3. `validate_action` loads `config/policy.yaml`.
4. It finds `legal action` in `truthfulness.unauthorized_consequence_terms`.
5. `hard_constraints.unauthorized_consequence_language_allowed` is false, so it returns `REJECTED` for constraint `PR-3`, field `message_body`.
6. The only automatic revision is SMS-to-email. That rule does not apply, so the graph escalates.
7. The decision is finalized. A later rewrite through `attempt_audit_rewrite` is refused.

Quiet hours take the other branch. The selector may prefer SMS because consent exists and recent replies were texts. The validator then rejects `PR-2.1` using `contact.consumer_quiet_hours`. The graph revises once to email and re-validates. Email is exempt, so the revision can be approved. The first rejection is kept on `policy_history` so the demo can still name the rule.
