#!/usr/bin/env python3
"""Check optional collaboration snapshots; no writes, network or command execution."""

import argparse
import itertools
import json
import re
import sys
from pathlib import Path

SCHEMA = Path(__file__).with_suffix(".schema.json")
LIVE = {"active", "handoff"}
LIMITS = [
    "Consistency of supplied snapshots only; freshness and source authenticity are not verified.",
    "Only supplied peers are checked; this is not an atomic claim or a lock.",
    "Evidence commands and sources are not executed or fetched; consistency is not acceptance.",
    "Paths are lexical and case-sensitive; aliases and undeclared dependencies are not checked.",
]


def load_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"non-JSON number: {value}")

    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=pairs, parse_constant=constant)


def validate_shape(value, rule, schema, path):
    """Evaluate the small schema vocabulary used by our bundled contract only."""
    if "$ref" in rule:
        rule = schema["$defs"][rule["$ref"].removeprefix("#/$defs/")]
    types = {"object": dict, "array": list, "string": str, "integer": int}
    if "type" in rule and type(value) is not types[rule["type"]]:
        raise ValueError(f"{path}: expected {rule['type']}")
    if "enum" in rule and value not in rule["enum"]:
        raise ValueError(f"{path}: unsupported value")
    if isinstance(value, str):
        if len(value) < rule.get("minLength", 0) or not value.strip():
            raise ValueError(f"{path}: empty string")
        if "pattern" in rule and not re.search(rule["pattern"], value):
            raise ValueError(f"{path}: invalid format")
    if isinstance(value, dict):
        properties = rule["properties"]
        missing = set(rule["required"]) - value.keys()
        extra = value.keys() - properties.keys()
        if missing or extra:
            raise ValueError(f"{path}: missing {sorted(missing)}, unknown {sorted(extra)}")
        for key, item in value.items():
            validate_shape(item, properties[key], schema, f"{path}.{key}")
    if isinstance(value, list):
        if len(value) < rule.get("minItems", 0):
            raise ValueError(f"{path}: too few items")
        if rule.get("uniqueItems") and len({json.dumps(x, sort_keys=True) for x in value}) != len(value):
            raise ValueError(f"{path}: duplicate item")
        for index, item in enumerate(value):
            validate_shape(item, rule["items"], schema, f"{path}[{index}]")


def keyed(items, key, path):
    result = {item[key]: item for item in items}
    if len(result) != len(items):
        raise ValueError(f"{path}: duplicate {key}")
    return result


def validate_record(record, path):
    for name, key in (("dependencies", "task_id"), ("decisions", "id")):
        keyed(record[name], key, f"{path}.{name}")
    for value in record["ownership"]["paths"]:
        # Literal repository-relative file paths or directories ending in '/'.
        parts = value.removesuffix("/").split("/")
        if (any(part in ("", ".", "..") for part in parts)
                or any(char in value for char in "\\:*?[]")
                or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            raise ValueError(f"{path}.ownership.paths: use canonical relative paths, no globs")


def overlaps(left, right):
    return (left.rstrip("/") == right.rstrip("/")
            or (left.endswith("/") and right.startswith(left))
            or (right.endswith("/") and left.startswith(right)))


def check(receipts, context, schema):
    validate_shape(context, schema["$defs"]["context"], schema, "context")
    tasks = keyed(context["tasks"], "task_id", "context.tasks")
    for index, task in enumerate(context["tasks"]):
        validate_record(task, f"context.tasks[{index}]")
    seen = set()
    for index, receipt in enumerate(receipts):
        path = f"receipts[{index}]"
        validate_shape(receipt, schema["$defs"]["receipt"], schema, path)
        validate_record(receipt, path)
        identity = (receipt["repository"], receipt["task_id"], receipt["session_id"], receipt["revision"])
        if identity in seen:
            raise ValueError(f"{path}: duplicate receipt identity")
        seen.add(identity)

    errors = []

    def error(code, path):
        errors.append({"code": code, "path": path})

    for index, receipt in enumerate(receipts):
        path = f"receipts[{index}]"
        if receipt["repository"] != context["repository"]:
            error("repository_mismatch", path)
            continue
        task = tasks.get(receipt["task_id"])
        if task is None:
            error("task_unknown", path)
            continue
        for field, code in (("revision", "stale_revision"), ("state", "state_mismatch")):
            if receipt[field] != task[field]:
                error(code, f"{path}.{field}")
        if receipt["session_id"] != task["owner_session"]:
            error("owner_mismatch", f"{path}.session_id")
        for field in ("base_sha", "head_sha"):
            if receipt["candidate"][field] != task["candidate"][field]:
                error("candidate_mismatch", f"{path}.candidate.{field}")
        for field in ("paths", "shared_interfaces"):
            if set(receipt["ownership"][field]) != set(task["ownership"][field]):
                error("ownership_mismatch", f"{path}.ownership.{field}")
        for field, key, version, code in (
                ("dependencies", "task_id", "head_sha", "dependency_mismatch"),
                ("decisions", "id", "revision", "stale_decision")):
            actual = {item[key]: item[version] for item in receipt[field]}
            expected = {item[key]: item[version] for item in task[field]}
            if actual != expected:
                error(code, f"{path}.{field}")
        for number, evidence in enumerate(receipt["evidence"]):
            if evidence["candidate_sha"] != receipt["candidate"]["head_sha"]:
                error("evidence_sha_mismatch", f"{path}.evidence[{number}]")
        handoff = receipt.get("handoff")
        if receipt["state"] == "handoff":
            if not handoff or handoff["to_session"] == receipt["session_id"]:
                error("handoff_invalid", f"{path}.handoff")
        elif handoff is not None:
            error("handoff_invalid", f"{path}.handoff")

    for (left_index, left), (right_index, right) in itertools.combinations(enumerate(receipts), 2):
        if (left["repository"] != right["repository"]
                or left["state"] not in LIVE or right["state"] not in LIVE):
            continue
        path = f"receipts[{left_index}],receipts[{right_index}]"
        if left["task_id"] == right["task_id"]:
            error("duplicate_claim", path)
        left_scope, right_scope = left["ownership"], right["ownership"]
        if any(overlaps(a, b) for a in left_scope["paths"] for b in right_scope["paths"]):
            error("path_conflict", path)
        if set(left_scope["shared_interfaces"]) & set(right_scope["shared_interfaces"]):
            error("interface_conflict", path)
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("check")
    command.add_argument("receipt", type=Path)
    command.add_argument("--context", type=Path, required=True)
    command.add_argument("--peer", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    try:
        receipts = [load_json(path) for path in [args.receipt, *args.peer]]
        errors = check(receipts, load_json(args.context), load_json(SCHEMA))
        result = {"status": "conflict" if errors else "consistent",
                  "errors": errors, "checked_receipts": len(receipts), "limits": LIMITS,
                  "behavior_verification": "not_performed",
                  "receipts_without_evidence": sum(not item["evidence"] for item in receipts),
                  "evidence_results": {name: sum(evidence["result"] == name
                                               for item in receipts for evidence in item["evidence"])
                                       for name in ("passed", "failed", "pending", "not_run", "skipped", "unavailable", "unknown")}}
        code = 1 if errors else 0
    except (OSError, ValueError, RecursionError) as exc:
        result = {"status": "invalid_input", "errors": [{"code": "invalid_input", "message": str(exc)}],
                  "limits": LIMITS}
        code = 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
