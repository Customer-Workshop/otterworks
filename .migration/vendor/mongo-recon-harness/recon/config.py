"""Versioned inputs: mapping spec, tolerance record, canonicalization rules.

All three are loaded from JSON files and cited in every report. The harness refuses to
run if any is missing a version field, because an unversioned input cannot be cited.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class FieldMapping:
    source: str
    target: str
    source_type: str
    bson_type: str
    rules: list[str] = field(default_factory=list)  # canonicalization rule names, in order


@dataclass(frozen=True)
class EmbedMapping:
    array_path: str
    child_table: str
    # Optional filter on the child table when only a subset embeds.
    child_where: str | None = None


@dataclass(frozen=True)
class CollectionMapping:
    collection: str
    root_table: str
    key_source: list[str]
    key_target: str
    fields: list[FieldMapping]
    embeds: list[EmbedMapping] = field(default_factory=list)
    root_where: str | None = None


@dataclass(frozen=True)
class MappingSpec:
    version: str
    collections: list[CollectionMapping]


@dataclass(frozen=True)
class Tolerances:
    version: str
    full_diff_row_threshold: int = 100_000
    sample_size: int = 1_000
    numeric_abs_tol: float = 0.0
    aggregate_rel_tol: float = 0.0
    source_concurrency: int = 1


@dataclass(frozen=True)
class CanonRule:
    rule: str
    applies_to: str
    params: dict[str, Any] = field(default_factory=dict)


def _require_version(data: dict, path: Path) -> str:
    version = data.get("version")
    if not version:
        raise ConfigError(f"{path}: missing 'version'; unversioned inputs cannot be cited in evidence")
    return str(version)


def load_mapping_spec(path: Path) -> MappingSpec:
    data = json.loads(path.read_text())
    version = _require_version(data, path)
    collections = []
    for c in data.get("collections", []):
        fields_ = [FieldMapping(
            source=f["source"], target=f["target"],
            source_type=f.get("source_type", ""), bson_type=f.get("bson_type", ""),
            rules=list(f.get("rules", [])),
        ) for f in c.get("fields", [])]
        embeds = [EmbedMapping(
            array_path=e["array_path"], child_table=e["child_table"],
            child_where=e.get("child_where"),
        ) for e in c.get("embeds", [])]
        key = c.get("key") or {}
        if not key.get("source") or not key.get("target"):
            raise ConfigError(
                f"{path}: collection '{c.get('collection')}' has no comparison key; "
                "ObjectId-only collections must declare one in the mapping spec")
        collections.append(CollectionMapping(
            collection=c["collection"], root_table=c["root_table"],
            key_source=list(key["source"]), key_target=key["target"],
            fields=fields_, embeds=embeds, root_where=c.get("root_where"),
        ))
    if not collections:
        raise ConfigError(f"{path}: mapping spec has no collections")
    return MappingSpec(version=version, collections=collections)


def load_tolerances(path: Path) -> Tolerances:
    data = json.loads(path.read_text())
    version = _require_version(data, path)
    return Tolerances(
        version=version,
        full_diff_row_threshold=int(data.get("full_diff_row_threshold", 100_000)),
        sample_size=int(data.get("sample_size", 1_000)),
        numeric_abs_tol=float(data.get("numeric_abs_tol", 0.0)),
        aggregate_rel_tol=float(data.get("aggregate_rel_tol", 0.0)),
        source_concurrency=int(data.get("source_concurrency", 1)),
    )


def load_canon_rules(path: Path) -> list[CanonRule]:
    data = json.loads(path.read_text())
    rules = data if isinstance(data, list) else data.get("rules", [])
    return [CanonRule(rule=r["rule"], applies_to=r.get("applies_to", "*"),
                      params=dict(r.get("params", {}))) for r in rules]
