# Evaluation (module B) and scoring (module C)

## Key files
| File | Role |
|---|---|
| `app/evaluation/prompts.py` | `SYSTEM` (verdict definitions, quote rules, root_of rule), SOP/evidence blocks, per-subcategory prompt; `PROMPT_VERSION` |
| `app/evaluation/assessor.py` | `Assessor.assess`: one call per subcategory, validation, retries, L2/L3 without evidence |
| `app/evaluation/verifier.py` | `SourceIndex.contains`: exact or fuzzy (rapidfuzz `partial_ratio` ≥ 90) quote match |
| `app/evaluation/engine.py` | `evaluate()` pipeline; `cache_key()`; `ENGINE_VERSION` |
| `app/evaluation/offline.py` | heuristic verdicts for ~8 mechanical checks (e.g. Q01-3-01 non-numeric spec, Q01-8-02 revision, Q01-11-01 image text vs step text) |
| `app/scoring/scorer.py` | `normalize`, level/subcategory/core/dimension roll-up, gate, overall status |
| `app/scoring/improvements.py` | work-element overlay, improvement guide, `OWNER_BY_SUBCATEGORY` |
| `rubrics/policy@1.0.json` | points, weights, blocking checks, benchmark (ADR 0007) |
| `tests/unit/test_scorer.py`, `test_evaluation.py` | rules and pipeline tests |

## How evaluation works
1. Levels to ask the LLM: always L1; L2/L3 only if evidence of that level is attached (ADR 0005).
2. Prompt prefix (cached): system + SOP JSON (+ evidence JSON). Suffix: core context + one subcategory's checks with criteria per level.
3. The first subcategory call runs alone (writes the cache), the rest run concurrently.
4. Each answer (`SubcategoryAssessment`) is validated: unknown ids/levels dropped; a `met` must have at least one quote found in the source, otherwise it isn't accepted. Missing/rejected checks are re-asked once; still missing → `evidence_missing`, confidence 0, "Not reliably assessed".
5. Quotes are kept with `verified` true/false; if none of a verdict's quotes verify, confidence is capped at 0.3. `work_element_ids` are filtered to real ids; `root_of` must be another check in the same core.

## How scoring works (deterministic)
1. `normalize`: N/A without rationale → `evidence_missing`; `root_of` dropped unless the root is itself a gap at the same level; `blocking` = gap on a policy blocking check.
2. Level score per subcategory = weighted mean of points over met/partial/gap checks that aren't consequences (`root_of`). `evidence_completeness` = (applicable − missing) / applicable.
3. Core = weighted mean of subcategories; dimension score = L1 of its assessed cores; overall = L1 across assessed cores (ADR 0006).
4. Gate: `blocked` if any blocking gap; else `evidence_required` if any required level (L2, L3) has missing evidence; else `passed`.
5. Status: `benchmark_verified` only if L1 ≥ benchmark and gate `passed`.
6. Overlay per work element: `blocked` / `gap` / `evidence` / `verified` / `no_findings` (nothing linked; never shown as a pass).
7. Improvements: must_fix (blocking gaps) → benchmark (other gaps, L1 partials) → evidence (one item per level if nothing was uploaded for it, else per subcategory).

## Rules for changing it
- Never add LLM calls to `scoring/`.
- Prompt wording or `LLMCheck` schema change → bump `PROMPT_VERSION`. Scoring/overlay/improvement logic change → bump `ENGINE_VERSION`. Policy change → bump policy `version`.
- New rule? Add a test in `test_scorer.py` first; keep `test_deterministic_regardless_of_input_order` passing.
- Changing points, weights or the blocking list is an owner decision (ADR 0007).
