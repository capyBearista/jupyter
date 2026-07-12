# Review log

This is a public schema template. No substantive review rows, findings, or
consequential changes exist yet.

## Method and code reviews

| Review ID | Date | Scope | Finding | Disposition | Consequential change |
| --- | --- | --- | --- | --- | --- |
| G3-IRR-20260712 | 2026-07-12 | Independent research review (`independent-research-reviewer`, model configured by project agent); `notebooks/02_transparent_metrics_and_keyness.ipynb` | No blockers. Formula, denominators, directions, and robustness across the nested shared-stage subset were confirmed. Contextualization was required for title conventions/boilerplate, token-frequency asymmetry, stopword exceptions, named entities, lexicon overlaps, and descriptive-only/annotation-required/prohibited claim boundaries. | Accepted: human/orchestrator accepted all contextualization guardrails. No coding labels changed and no annotation decision was involved. | Notebook 02 implements the guardrails. |
| G3-PUB-LINEAGE-20260712 | 2026-07-12 | Standard code reviews of final publication/lineage contracts | Actionable validator, publication, path, and test findings were accepted and fixed. Two over-scoped demands—per-row metrics derivation proof and reopening interim input for missing-category provenance—conflicted with the frozen bounded contract and were rejected. Oracle-approved canonical evidence/stage consistency and strict JSON type comparison were then accepted and fixed; final focused review had no actionable findings. | Accepted and rejected as stated; bounded-contract decisions retained. | Validation strengthened; scientific serialization and results unchanged. |
| G3-NOTEBOOK-20260712 | 2026-07-12 | Notebook code/visual review; `notebooks/02_transparent_metrics_and_keyness.ipynb` | Initial minor shared-schema and label-collision findings, plus standalone caveat/scale/grouping findings, were accepted and fixed. Final title mismatch was accepted and fixed. | Accepted and fixed. | Figures and notebook were re-executed; result counts did not change, and presentation and claim boundaries improved. |

## Post-draft case critiques

| Critique ID | Date | Draft/case scope | Finding | Disposition | Consequential change |
| --- | --- | --- | --- | --- | --- |
