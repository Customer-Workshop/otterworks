"""The four check tiers, in order of cost. Each returns a TierResult; the engine gates:
Tier 1 must be green before anything else runs.

All comparisons happen post-canonicalization through the mapping spec, never raw.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from .canon import MISSING, Canonicalizer
from .config import CollectionMapping, MappingSpec, Tolerances


@dataclass
class Finding:
    collection: str
    check: str
    detail: str
    source_value: Any = None
    target_value: Any = None
    rules_applied: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"collection": self.collection, "check": self.check, "detail": self.detail,
                "source_value": repr(self.source_value), "target_value": repr(self.target_value),
                "rules_applied": self.rules_applied}


@dataclass
class TierResult:
    tier: int
    name: str
    passed: bool
    checks_run: int
    findings: list[Finding]
    stats: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"tier": self.tier, "name": self.name, "passed": self.passed,
                "checks_run": self.checks_run, "stats": self.stats,
                "findings": [f.as_dict() for f in self.findings]}


def _get_path(doc: dict, path: str) -> Any:
    cur: Any = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return MISSING
        cur = cur[part]
    return cur


def tier1_counts(spec: MappingSpec, source, target) -> TierResult:
    """Counts THROUGH the mapping: root docs vs root rows; embedded array cardinality vs
    child-table rows. A naive docs-vs-rows count is wrong by construction for embeds."""
    findings, checks = [], 0
    for c in spec.collections:
        checks += 1
        src_n = source.row_count(c.root_table, c.root_where)
        tgt_n = target.doc_count(c.collection)
        if src_n != tgt_n:
            findings.append(Finding(c.collection, "root_count",
                                    f"rows({c.root_table})={src_n} vs docs={tgt_n}"))
        for e in c.embeds:
            checks += 1
            child_n = source.row_count(e.child_table, e.child_where)
            emb_n = target.embedded_count(c.collection, e.array_path)
            if child_n != emb_n:
                findings.append(Finding(c.collection, "embed_cardinality",
                                        f"rows({e.child_table})={child_n} vs sum(len({e.array_path}))={emb_n}"))
    return TierResult(1, "counts_through_mapping", not findings, checks, findings)


def _agg_close(a: Any, b: Any, rel_tol: float) -> bool:
    if a is None and b is None:
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        denom = max(abs(a), abs(b), 1e-12)
        return abs(a - b) <= rel_tol * denom
    return a == b


# Rules that remap what counts as null/present. Aggregates are computed natively on each
# side (pre-canonicalization), so null_rate/distinct/min/max are not comparable for fields
# carrying these rules; they are deferred to Tier 3's keyed post-canonicalization diff.
NULL_SEMANTIC_RULES = {"empty_string_is_null", "null_missing_equiv"}


def tier2_aggregates(spec: MappingSpec, tol: Tolerances, canon: Canonicalizer,
                     source, target) -> TierResult:
    findings, checks = [], 0
    deferred: list[str] = []
    sum_not_comparable: list[str] = []
    for c in spec.collections:
        for f in c.fields:
            checks += 1
            s = source.field_aggregates(c.root_table, f.source, c.root_where)
            t = target.field_aggregates(c.collection, f.target)
            stats_to_check = ("null_rate", "distinct_count", "sum", "min", "max")
            if NULL_SEMANTIC_RULES & set(f.rules):
                stats_to_check = ("sum",)
                deferred.append(f"{c.collection}.{f.target}")
            for stat in stats_to_check:
                sv, tv = s.get(stat), t.get(stat)
                if stat == "sum" and sv is None:
                    # The source has no numeric sum for this field (non-numeric column, or
                    # every value NULL). SQL SUM() answers NULL there while MongoDB's $sum
                    # answers 0 over the same absence, so the two sides state the same fact
                    # in different vocabularies and the comparison carries no information.
                    # Tier 3's keyed, post-canonicalization diff covers the field's values.
                    sum_not_comparable.append(f"{c.collection}.{f.target}")
                    continue
                if stat in ("min", "max", "sum"):
                    sv, _ = canon.apply(sv, f.rules)
                    tv, _ = canon.apply(tv, f.rules)
                    sv = float(sv) if hasattr(sv, "__float__") and not isinstance(sv, bool) else sv
                    tv = float(tv) if hasattr(tv, "__float__") and not isinstance(tv, bool) else tv
                if not _agg_close(sv, tv, tol.aggregate_rel_tol):
                    findings.append(Finding(c.collection, f"aggregate_{stat}",
                                            f"field {f.source}->{f.target}", sv, tv, f.rules))
    stats: dict[str, Any] = {}
    if deferred:
        stats["deferred_to_tier3"] = deferred
    if sum_not_comparable:
        stats["sum_not_comparable"] = sum_not_comparable
    return TierResult(2, "per_field_aggregates", not findings, checks, findings, stats)


def tier3_diffs(spec: MappingSpec, tol: Tolerances, canon: Canonicalizer,
                source, target, seed: int = 0) -> TierResult:
    """Full keyed diff below the tolerance row threshold; keyed stratified sampling above."""
    findings, checks = [], 0
    stats: dict[str, Any] = {}
    rng = random.Random(seed)
    for c in spec.collections:
        n = source.row_count(c.root_table, c.root_where)
        sampled = n > tol.full_diff_row_threshold
        keys: list[Any] | None = None
        src_rows = {tuple(r[k] for k in c.key_source): r
                    for r in source.fetch_keyed(c.root_table, c.key_source,
                                                [f.source for f in c.fields], c.root_where)}
        if sampled:
            population = sorted(src_rows)
            take = min(tol.sample_size, len(population))
            chosen = set(population[:2] + population[-2:] + rng.sample(population, take))
            src_rows = {k: src_rows[k] for k in chosen}
            keys = [k[0] if len(k) == 1 else k for k in chosen]
            stats[c.collection] = {"mode": "stratified_sample", "population": n,
                                   "sampled": len(src_rows),
                                   "coverage": round(len(src_rows) / n, 6) if n else 1.0}
        else:
            stats[c.collection] = {"mode": "full_diff", "population": n}
        tgt_docs = {}
        for d in target.fetch_keyed(c.collection, c.key_target,
                                    [f.target for f in c.fields], keys):
            kv = _get_path(d, c.key_target)
            tgt_docs[(kv,) if not isinstance(kv, tuple) else kv] = d
        for k, row in src_rows.items():
            checks += 1
            doc = tgt_docs.get(k)
            if doc is None:
                findings.append(Finding(c.collection, "missing_doc", f"key={k}"))
                continue
            for f in c.fields:
                sv = row.get(f.source, MISSING)
                tv = _get_path(doc, f.target)
                ok, fired = canon.equal(sv, tv, f.rules, tol.numeric_abs_tol)
                if not ok:
                    findings.append(Finding(c.collection, "field_diff",
                                            f"key={k} field {f.source}->{f.target}",
                                            sv, tv, fired))
        for k in tgt_docs:
            if k not in src_rows and not sampled:
                checks += 1
                findings.append(Finding(c.collection, "extra_doc", f"key={k}"))
    return TierResult(3, "keyed_diffs", not findings, checks, findings, stats)


def tier4_parity(ops: list[dict], canon: Canonicalizer, tol: Tolerances,
                 run_source, run_target) -> TierResult:
    """Replay recorded representative operations against both stacks. `run_source` and
    `run_target` execute one recorded op and return a list of result rows/docs; the unit
    supplies them (this is the one tier that is never delegated)."""
    findings, checks = [], 0
    for op in ops:
        checks += 1
        rules = list(op.get("rules", []))
        s = [tuple(sorted((k, canon.apply(v, rules)[0]) for k, v in row.items()))
             for row in run_source(op)]
        t = [tuple(sorted((k, canon.apply(v, rules)[0]) for k, v in row.items()))
             for row in run_target(op)]
        if sorted(map(repr, s)) != sorted(map(repr, t)):
            findings.append(Finding(op.get("collection", "?"), "parity_mismatch",
                                    f"op '{op.get('name', '?')}' result sets differ "
                                    f"(source {len(s)} rows, target {len(t)} rows)"))
    return TierResult(4, "app_level_parity", not findings, checks, findings)
