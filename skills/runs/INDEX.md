# Worked Runs — Index

Tag table used for trait-based retrieval. One row per run; see
[../../docs/design/knowledge-system.md](../../docs/design/knowledge-system.md).

| Run | Dataset / Scene | Recon | Traits | Modules | Outcome |
| --- | --- | --- | --- | --- | --- |

*Empty. Populated as sessions are driven and distilled.*

---

## Where the raw numbers live

**The per-capture measurement tables are not in this file.** They are in
[EVIDENCE.md](EVIDENCE.md), and they were moved there because the two things were
sharing a file and are not the same kind of thing:

| | INDEX.md (this file) | EVIDENCE.md |
| --- | --- | --- |
| Answers | "has a scene like this been solved before?" | "where does this claim come from?" |
| Keyed on | derived scene traits | the claim being cited |
| Read | while planning, before running anything | when checking a claim, or re-running one |
| A row is | a precedent to follow | a measurement to trace, **never** a plan |
| Scene names | a retrieval key | a provenance record |

Sharing one file meant a reader who fetched it to plan got a page of scene-named
measurement tables under a heading promising precedent, and the invitation to plan
from a row is exactly the misuse both files warn against. Fetch the one whose
question you are actually asking.
