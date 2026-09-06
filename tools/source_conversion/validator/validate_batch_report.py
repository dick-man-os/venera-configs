"""Validate the batch extension using its bounded, checked-in JSON schema.

Only the explicit keyword subset used by this schema is supported; unknown
keywords fail closed so schema extensions cannot silently weaken validation.
"""
import json
from collections import Counter
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema/batch_report.schema.json"


def _validate(value, schema, path, errors):
    known = {"$schema", "title", "type", "const", "enum", "anyOf", "properties",
             "required", "additionalProperties", "items", "minLength", "minItems", "minimum", "uniqueItems"}
    if set(schema) - known:
        errors.append(path + ": unsupported schema keyword")
        return
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            attempt = []
            _validate(value, option, path, attempt)
            if not attempt:
                return
        errors.append(path + ": no matching schema alternative")
        return
    if "const" in schema and value != schema["const"]:
        errors.append(path + ": invalid constant")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(path + ": invalid enum")
    types = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool, "null": type(None)}
    expected = schema.get("type")
    if expected:
        names = expected if isinstance(expected, list) else [expected]
        if not any(type(value) is types[name] for name in names):
            errors.append(path + ": wrong type")
            return
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(path + ": missing " + key)
        for key, child in value.items():
            if key in properties:
                _validate(child, properties[key], path + "." + key, errors)
            elif schema.get("additionalProperties") is False:
                errors.append(path + ": unexpected " + key)
            elif isinstance(schema.get("additionalProperties"), dict):
                _validate(child, schema["additionalProperties"], path + "." + key, errors)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(path + ": too few items")
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            errors.append(path + ": duplicate items")
        if "items" in schema:
            for i, child in enumerate(value):
                _validate(child, schema["items"], f"{path}[{i}]", errors)
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        errors.append(path + ": string too short")
    if type(value) is int and value < schema.get("minimum", value):
        errors.append(path + ": below minimum")


def validate_batch_report(data):
    errors = []
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    _validate(data, schema, "batch", errors)
    if errors:
        return sorted(errors)
    rows = data["candidates"]
    identities = [(item["project"], item["sourceId"]) for item in rows]
    if identities != sorted(set(identities)):
        errors.append("batch: unordered or duplicate identities")
    if data["summary"]["candidates"] != len(rows):
        errors.append("batch: candidate count mismatch")
    counts = Counter(item["state"] for item in rows)
    if any(counts[key] != value for key, value in data["summary"]["states"].items()):
        errors.append("batch: state count mismatch")
    for row in rows:
        expected_action = {"ELIGIBLE": "review-create", "UPDATE_AVAILABLE": "review-update"}.get(row["state"], "skip")
        if row["action"] != expected_action:
            errors.append("batch: inconsistent action")
        if not row["imported"] and any(row[key] is not None for key in ("artifactId", "runtimeKey", "providerId", "fileName")):
            errors.append("batch: unreviewed local identity")
        for key in ("reasonCodes", "warnings"):
            if row[key] != sorted(set(row[key])):
                errors.append("batch: unordered " + key)
    return sorted(set(errors))


def validate_materialization_report(data):
    errors = []
    schema_path = SCHEMA_PATH.with_name("materialization_report.schema.json")
    _validate(data, json.loads(schema_path.read_text(encoding="utf-8")), "transaction", errors)
    if not errors:
        paths = [item["relativePath"] for item in data["targets"]]
        if paths != sorted(set(paths)):
            errors.append("transaction: unordered or duplicate targets")
        if data["operation"] == "update" and data["registryDelta"]:
            errors.append("transaction: UPDATE must preserve registry")
    return sorted(errors)
