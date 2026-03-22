# Format Fix Roadmap

## Status
- Total items: 23
- Implemented: 13 (ISSUE-01, ISSUE-02, ISSUE-03, ISSUE-04, ISSUE-05, ISSUE-06, ISSUE-07, ISSUE-08, ISSUE-13, ISSUE-14, ISSUE-15, ISSUE-16, ISSUE-20)
- Remaining: 10

## Items

### 1. FBaaS Watermark Stacking Fix (enterprise_fizzbuzz/infrastructure/fbaas.py)
**Status:** DONE
**Issues addressed:** ISSUE-07 (CRITICAL)
**Description:** Fix the cascading watermark accumulation bug in `FBaaSMiddleware.process()`. The `[Powered by FBaaS Free Tier]` watermark is re-appended to all accumulated results on every evaluation pass, causing lines to grow up to 291 characters. Guard against re-application by checking a metadata flag (e.g., `r.metadata.get("fbaas_watermarked")`) before appending, or scope the watermark to only the current evaluation's result rather than the full accumulated list. This is the single most visually broken output in the platform and must be fixed first.
**Files:**
- `enterprise_fizzbuzz/infrastructure/fbaas.py` (lines ~815-818)

---

### 2. FBaaS Billing Overflow + FinOps Banner Underflow + Proof Tree Width (enterprise_fizzbuzz/infrastructure/fbaas.py, enterprise_fizzbuzz/__main__.py, enterprise_fizzbuzz/infrastructure/verification.py)
**Status:** DONE
**Issues addressed:** ISSUE-08 (HIGH), ISSUE-03 (HIGH), ISSUE-13 (HIGH), ISSUE-14 (MEDIUM)
**Description:** Fix the three HIGH-severity overflow/underflow issues plus the related proof tree case-analysis cramming:
- **ISSUE-08:** FBaaS billing ledger row content exceeds the 60-char box, pushing the closing `|` to column 72. Truncate row content to `width - 6` chars or widen the box.
- **ISSUE-03:** FinOps banner "Currency" line renders at 55 chars instead of 61. The padding formula `max(0, 40 - len(...))` underestimates required padding. Replace with `.ljust()` or `:<57` f-string formatting.
- **ISSUE-13:** Proof tree horizontal rules extend up to 184 chars. Cap all horizontal rules at 60-70 characters and wrap long theorem statements with continuation indentation.
- **ISSUE-14:** All four case analysis results are crammed onto a single 123-char line. Print each case on its own indented line.
**Files:**
- `enterprise_fizzbuzz/infrastructure/fbaas.py` (lines ~978-981)
- `enterprise_fizzbuzz/__main__.py` (lines ~2980-2982)
- `enterprise_fizzbuzz/infrastructure/verification.py` (proof tree rendering)

---

### 3. Dashboard Width Standardization (multiple files)
**Status:** DONE
**Issues addressed:** ISSUE-05 (MEDIUM), ISSUE-06 (MEDIUM), ISSUE-20 (LOW)
**Description:** Standardize all dashboard output to a consistent width and indentation scheme. Currently five different widths exist (60, 62, 63, 66 chars) with inconsistent 0 vs 2-space left indentation. Adopt 60 content chars with 2-space indent (62 total) as the standard. Apply this to:
- Quantum, Self-Modify, Time-Travel, P2P, Kernel dashboards: add 2-space indent, adjust content width from 60 to 60 (adding indent makes total 62).
- Compliance dashboard: already 62, verify content fits.
- FinOps invoice: reduce from 66 to 62 chars (reformat line items to fit).
- Main banner: keep at 63 (it uses `+===+` borders, a distinct visual element). Alternatively standardize it too.
- Ontology class hierarchy: add 2-space indent per ISSUE-15.

This cycle establishes the width constant and applies it. Individual subsystem row-padding fixes are handled in subsequent cycles.
**Files:**
- `enterprise_fizzbuzz/__main__.py` (dashboard sections for Quantum, Kernel, P2P, Time-Travel, Self-Modify, FinOps invoice)
- `enterprise_fizzbuzz/infrastructure/compliance.py` (compliance dashboard)
- `enterprise_fizzbuzz/infrastructure/knowledge_graph.py` (ontology hierarchy output)

---

### 4. ASCII Art Banner + Subsystem Info Box Alignment (enterprise_fizzbuzz/__main__.py)
**Status:** DONE
**Issues addressed:** ISSUE-01 (MEDIUM), ISSUE-02 (MEDIUM), ISSUE-04 (MEDIUM), ISSUE-15 (LOW), ISSUE-16 (LOW)
**Description:** Fix all banner and info-box alignment issues:
- **ISSUE-01:** Pad each interior ASCII art line in the main FIZZBUZZ banner to exactly 63 chars total (61 content chars between the `|` delimiters). Currently lines vary between 61-63 chars.
- **ISSUE-02:** Across all 12+ subsystem info banners (Cache, Compliance, Quantum, Health, Knowledge Graph, Verification, Metrics, FBaaS, P2P, Kernel, Rate Limit, Self-Modify), content lines overflow the 61-char border by 1-2 chars. Replace manual padding arithmetic with `.ljust(width)` or `:<N` f-string formatting for all content lines.
- **ISSUE-04:** Kernel banner "Boot time" line uses `" " * (37 - len(...))` which produces inconsistent widths. Replace with a single f-string.
- **ISSUE-15:** OWL Class Hierarchy box lacks the standard 2-space indent. Add it.
- **ISSUE-16:** Inheritance annotation lines (81-85 chars) overflow the 60-char hierarchy box. Truncate or wrap annotations to fit within box width.
**Files:**
- `enterprise_fizzbuzz/__main__.py` (main banner, all subsystem info banners, kernel boot time)
- `enterprise_fizzbuzz/infrastructure/knowledge_graph.py` (OWL hierarchy indent and annotation overflow)

---

### 5. Dashboard Row Padding Fixes (multiple subsystem files)
**Status:** PENDING
**Issues addressed:** ISSUE-09 (LOW), ISSUE-10 (LOW), ISSUE-11 (MEDIUM), ISSUE-12 (LOW), ISSUE-17 (MEDIUM), ISSUE-18 (LOW)
**Description:** Fix per-subsystem row padding within dashboards so content rows match their border widths:
- **ISSUE-09:** Compliance stress bar line is 59 chars, should be 60. Adjust format string.
- **ISSUE-10:** Compliance posture data rows are 60 chars, borders are 62. Pad data rows to match.
- **ISSUE-11:** Paxos table header is 59 chars and data rows are 58 chars; borders are 62. Widen columns or right-pad to fill box.
- **ISSUE-12:** P2P gossip statistics data rows are 59 chars; borders are 60. Pad data rows.
- **ISSUE-17:** Kernel boot log truncates "swift" to "swi" with no ellipsis. Shorten the message to fit (e.g., "May your modulo ops be swift") or add an ellipsis.
- **ISSUE-18:** Prometheus metrics bookend box is 42 chars but metric lines reach 111 chars. Widen the bookend to match content width, or remove it in favor of blank-line separation.
**Files:**
- `enterprise_fizzbuzz/infrastructure/compliance.py` (stress bar, posture rows)
- `enterprise_fizzbuzz/__main__.py` (Paxos dashboard, P2P dashboard, Kernel boot log, Prometheus bookend)

---

### 6. Minor Text Fixes + Missing Features (multiple files)
**Status:** PENDING
**Issues addressed:** ISSUE-19 (LOW), ISSUE-21 (LOW), ISSUE-22 (LOW), ISSUE-23 (LOW)
**Description:** Fix remaining low-severity text and cosmetic issues:
- **ISSUE-19:** Prometheus counter metrics have redundant `_total_total` suffix. Rename base metrics from `efp_evaluations_total` and `efp_rule_matches_total` to `efp_evaluations` and `efp_rule_matches` so the automatic `_total` suffix produces correct names.
- **ISSUE-21:** Circuit breaker has no startup info banner. Add a `+---------+` info box matching the style of other subsystems (Cache, Compliance, FinOps, etc.) to confirm the circuit breaker is active.
- **ISSUE-22:** All output uses CRLF line endings. This is acceptable on Windows but causes `^M` artifacts through Unix tools. Document as expected behavior, or optionally add a `--unix-newlines` flag for cross-platform piping.
- **ISSUE-23:** Genetic algorithm fitness chart X-axis labels run together (`Gen 1Gen 5`). Add at least one space between generation labels.
**Files:**
- `enterprise_fizzbuzz/infrastructure/metrics.py` (counter naming)
- `enterprise_fizzbuzz/__main__.py` (circuit breaker banner, genetic chart X-axis labels, optionally CRLF handling)
