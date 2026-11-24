# AI disclosure

## Work on this presentation-readiness pass

A Cursor cloud coding agent assisted with implementation, tests, and documentation for the class-demo pass in this repository. That work was done under the author’s direction. The agent did not replace the deterministic policy engine, and it did not introduce a live language model.

The reasoning layer that the demo runs is still `DETERMINISTIC_MOCK` in `src/agent.py`. Intent phrases, action recommendations, and drafts in this build are deterministic code. `src/policy.py` remains the authority for consent, quiet hours, opt-outs, contact frequency, truthfulness, payment-plan authority, and escalation.

Evaluation numbers in `evals/synthetic_results.json` and the dashboard were produced by executing that code. They were not written in by hand.

## Author’s own use

<!-- AUTHOR: replace this section before submission. -->

[Author to complete. State which AI tools you used yourself, on which parts of the project, across the term, and what you reviewed, changed, or rejected. Dr. Nassiff asked for this disclosure. The paragraph above covers only the cloud-agent pass that prepared the demo, tests, and the documents added with it.]
