# Curation & Quality Audit Directive

## From the user

Pause new feature brainstorming. The platform is at 202,000+ lines across 229 files. Before adding anything else, I need a quality pass. The project's strength is that every module earns its place with genuine technical correctness AND a distinct comedic thesis. At 80+ infrastructure modules and 8 brainstorm rounds, that standard may have slipped. Some modules may be variations on a joke another module already tells better. Some may be technically sound but comedically redundant. Some may have drifted into "here is another real system applied to FizzBuzz" without a unique angle beyond the premise itself.

This directive replaces the brainstorm cycle temporarily. Follow the same workflow protocol you've been using (research/audit phase, plan phase, implement phase, docs update and git commit phase), but applied to curation instead of creation.

Do not add new modules. Do not start a Round 9 brainstorm. Do not expand the platform's surface area. Sharpen what exists.

---

## Phase 1: Audit (research phase)

Read every infrastructure module's docstring, its test file, and its FAQ entry (if any). For each module, answer three questions:

1. **What is this module's comedic thesis?** Not "it applies X to FizzBuzz" -- that's the premise of the whole project. What specific, distinct observation about software culture does this module make that no other module in the codebase already makes? The quantum simulator's thesis is "quantum supremacy is always negative for trivial problems." The compliance module's thesis is "GDPR and append-only architectures are philosophically irreconcilable." The SLA module's thesis is "the on-call rotation is one person at every escalation tier." Each of those is specific and couldn't be swapped with another module's joke. Can you say the same for every module added in rounds 4-7?

2. **Does this module overlap with another module's territory?** Examples to investigate:
   - `sli_framework.py` vs `sla.py` -- are these making the same point about observability theater?
   - `otel_tracing.py` vs `tracing.py` -- are two tracing modules saying two different things?
   - `capability_security.py` vs `auth.py` -- two security models for modulo arithmetic, but do they satirize different targets?
   - `billing.py` vs `fbaas.py` vs `finops.py` -- three monetization modules, are they each pulling their weight?
   - `fizzsql.py` vs `query_optimizer.py` vs `graph_db.py` vs `columnar_storage.py` -- four data access patterns, do they each have a distinct angle?
   - `distributed_locks.py` vs `paxos.py` vs `crdt.py` -- three distributed systems primitives, are they redundant?
   - `formal_verification.py` vs `dependent_types.py` vs `formal_grammar.py` -- three formal methods modules, same question.

3. **Is this module technically faithful?** The project's rule is that implementations must be genuinely correct. A CRDT should actually converge. A Kademlia DHT should actually route by XOR distance. A dependent type system should actually enforce types at the value level. Spot-check the newer modules for technical accuracy, not just structural presence.

Produce an audit report as `roadmaps/CURATION_AUDIT.md`. For each module, give it one of three ratings:

- **KEEP**: Distinct thesis, no significant overlap, technically sound.
- **SHARPEN**: Has potential but the comedic thesis is underdeveloped, or the docstrings/comments don't land the joke as well as the best modules do. Needs a rewrite pass on voice and framing, not on functionality.
- **MERGE or CUT**: Overlaps significantly with another module's territory and doesn't bring enough new material to justify its existence as a standalone file. Recommend either merging into the overlapping module or cutting entirely.

Be honest. The project is better at 70 sharp modules than 85 modules where 15 are filler. Cutting is not failure; it's editing.

---

## Phase 2: Plan

Based on the audit, produce a remediation plan in the same `CURATION_AUDIT.md` file. For each SHARPEN or MERGE/CUT module, specify:

- **SHARPEN items**: What the rewrite should focus on. New docstring angle? Sharper comments? A missing joke that ties the module to the broader Bob McFizzington cinematic universe? A FAQ entry it deserves but doesn't have?
- **MERGE items**: Which module absorbs it, and what (if anything) from the absorbed module is worth preserving.
- **CUT items**: Confirm the module and its test file should be removed. Note any references in `__main__.py`, `config.yaml`, the README, or other modules that need cleanup.

---

## Phase 3: Implement

Execute the plan. One commit per action (one commit per sharpen rewrite, one commit per merge, one commit per cut). Each commit should leave the test suite passing.

For SHARPEN rewrites: focus on docstrings, comments, class/method descriptions, dashboard text, and error messages. The code logic stays the same. The voice gets sharper. Read the best modules in the codebase (compliance.py, sla.py, cache.py, chaos.py, quantum.py) as reference for the standard. Every module should read like it was written by someone who has spent too long in enterprise software and is channeling their frustration into technically perfect satire.

For MERGE operations: preserve any genuinely unique functionality from the absorbed module. Don't just delete -- transplant the best bits.

For CUT operations: remove the module, its test file, its CLI flags, its config entries, its README references, and any imports in other modules. Clean removal with no dangling references.

---

## Phase 4: Docs update and git commit

After all changes:

- Update the README's line count, file count, test count, and module list.
- Update `CLAUDE.md` if the architecture description changed.
- Update `docs/architecture.md`, `docs/testing.md`, and `docs/SUBSYSTEMS.md` to reflect any removed or merged modules.
- Archive this directive to `roadmaps/archive/CURATION_AUDIT.md` when complete.
- Update the brainstorm report's header to reflect the new line/file/test counts.
- Commit everything.

---

## Guiding principle

The project is art because it's curated, not because it's large. A 180,000-line codebase where every module is a precisely aimed satirical dart is better than a 202,000-line codebase where some modules are just "another thing that exists." The audience for this project will read the module list and the docstrings. Every entry should make them laugh or make them think. If it does neither, it doesn't belong.

The bar is: could this module's docstring be quoted in the README FAQ and hold its own next to the GDPR erasure paradox, the single-node Raft election, and the quantum advantage ratio that's always negative? If yes, keep it. If no, sharpen it until it can, or cut it.
