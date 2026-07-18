# Persistent formula-model cache — findings (spike)

Goal: keep the loaded Arelle taxonomy model alive across validations so the
steady-state formula phase drops from ~2 min toward "seconds + evaluation time".
Acceptance criterion: findings **byte-identical** cached vs uncached
(fast-but-different is a fail).

**Outcome: no cache shipped.** A reused (warm) controller is both no faster *and*
not identical. What this spike ships is the fix it surfaced — deterministic
finding extraction — plus this write-up. Numbers below are from live 4.2 runs
(the `hero_pkg.zip`, 52 assertions evaluated).

## 1. Arelle does not reuse the loaded taxonomy

Keeping one long-lived `CntlrCmdLine` and validating twice gives **no speedup** —
Arelle re-parses the entire taxonomy DTS into a fresh `ModelXbrl` on every model
load. Measured, warm controller vs fresh:

| run | wall |
|-----|------|
| cached, cold controller | 124 s |
| cached, warm controller (reused) | 113 s |
| uncached, fresh controller | 109 s |

The warm run is not faster than a fresh one (within noise; the ~110 s DTS parse
dominates and is re-done every time). Corroborating: `ModelManager` exposes only
`load` / `loadCustomTransforms` / `reloadViews` — no "load taxonomy once, attach
instances" hook; Arelle has no model serialization / fast-reload (`saveDTSpackage`
only writes the DTS files out as a zip); `--keepOpen` doesn't let a *different*
instance reuse a model's DTS.

## 2. The warm controller breaks findings-identity (isolation fail)

The acceptance check compares a canonical (order-independent) view of the
findings + per-rule results.

- **Two fresh uncached runs → byte-identical** (0 rules differ, findings equal).
  Arelle's *evaluation* is deterministic.
- **Cached (warm controller) vs uncached → different**, and the two cached runs
  even differed **from each other**.

So the reused controller accumulates state across `run()` calls that changes the
results — even though each run closes its report model (`--keepOpen` off). This
is exactly the shared-mutable-state hazard the criterion guards against. The
in-process warm controller **cannot guarantee isolation**, so it is not shipped.

## 3. The real bug this surfaced — non-deterministic finding extraction (fixed)

Arelle emits per-fact assertion messages in a **non-deterministic order**. The
old extraction kept "the first-seen" message/location per rule, so the *same*
run produced different findings each time — independent of any caching. Fixed in
`findings_from_arelle_records` / `rule_results_from_records`: group by rule id
and pick the lexicographically-smallest message (and sort by rule id), so the
mapping is order-independent. Pinned by
`test_arelle_adapter.test_findings_are_order_independent`. With this fix, two
fresh runs are byte-identical (§2).

## 4. What is (already) safely cached

The genuinely reusable expensive artifacts are cached to disk and unchanged:
the expanded inner taxonomy packages (`expand_taxonomy_packages`) and the built
eurofiling package. The dominant cost — the DTS parse — is inside Arelle's
per-model load and is not safely cacheable in-process.

## 5. Recommendation (real fix, future work)

Reaching seconds-per-validation requires a resident, pre-compiled model that new
instances validate against **without** re-parsing the DTS, with isolation
enforced structurally:

1. **Out-of-process warm-model service** — a worker that loads the DTS +
   compiles the formula linkbase once and validates instances on request, each
   instance loaded into a *fresh* `ModelXbrl` that references pre-parsed,
   immutable schema documents (or a cloned model). This is a focused
   Arelle-internals project, not a config flag, and it is where the isolation
   guarantee must be engineered and re-verified against this acceptance test.
2. Precompute assertion→cell bindings offline and evaluate the common rule
   shapes (sums/inequalities) ourselves, using Arelle only as an authoritative
   cross-check — trades fidelity for speed.

Neither is a safe in-process cache, which is why the spike ships the correctness
fix and this ceiling rather than a `FORMULA_MODEL_CACHE` flag that would be
default-on, no faster, and non-reproducible.
