# AI assistance

AI tools may assist with drafting scaffold documentation, code suggestions, and
review prompts. Human maintainers remain responsible for factual claims,
provenance, methodology, citations, and all publication decisions. AI assistance
is not evidence, annotation ground truth, or a source of substantive research
findings.

## Committed custom agents

The committed reviewer, `.opencode/agents/independent-research-reviewer.md`, is
a fresh child subagent for each review. It is read-only to the project through
`read`, `glob`, and `grep` permissions and is advisory only.

The committed consultant,
`.opencode/agents/blinded-annotation-consultant.md`, is a fresh child subagent
with `permission: deny`. Its parent supplies only the frozen guide and one
sanitized official/short-title pair. It has no filesystem, network, or project
context and receives no initial human labels, sampling strata, metrics, or
corpus results. A human records the final labels and dispositions. The
consultant's suggestions are non-authoritative; it is not a second annotator or
a reliability source.

Both agent frontmatter files pin the model ID
`openrouter/z-ai/glm-5.2`. Pinning identifies the configured model, but cannot
guarantee reproducible model output.

## Public records

The public schemas are `data/annotations/llm_consultations.csv` for annotation
consultations and `reports/review_log.md` for method/code reviews and
post-draft case critiques. They intentionally contain no substantive rows or
findings yet. Consultation records identify the sanitized packet hash,
guide/agent version, model configuration, output reference, advisory
suggestions, human labels, disposition, changes, and rationale. Review records
separate findings, dispositions, and consequential changes by review type.
These templates avoid leaking blinded sampling or metric information into
consultation packets.

## Gate 1 scope

This Gate 1 documentation records local audit values supplied for the project;
it does not claim that AI independently verified corpus coverage. Any future
model-assisted consultation must retain enough protocol and disposition metadata
for independent human review.

The future canonical narrative report path is `reports/pilot_report.md`.
