from __future__ import annotations

import re
from typing import Any

from .models import RedactionAssessment

SENSITIVE_KEY = re.compile(
    r"(?:"
    r"authorization|"
    r"password|"
    r"passwd|"
    r"secret|"
    r"token|"
    r"api[_-]?key|"
    r"private[_-]?key|"
    r"client[_-]?secret"
    r")",
    re.IGNORECASE,
)
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)
ABSOLUTE_PATH = re.compile(
    r"(?:"
    r"(?<![A-Za-z0-9_.-])/(?:home|Users|var|tmp|private|opt)/[^\s]+"
    r"|"
    r"(?<![A-Za-z0-9_.-])[A-Za-z]:\\[^\s]+"
    r")"
)
# A full git object id: exactly 40 hex characters standing alone.
#
# A commit SHA is globally searchable, so an event carrying one alongside a
# repository pseudonym is not pseudonymous -- the pseudonym is decorative. This
# check existed for absolute paths and sensitive keys and would have caught
# neither a bare SHA nor, as the module has long noted, a repository-relative
# source path; the SDK adapter carried a raw snapshot id past it for exactly
# that reason.
#
# Bounded to 40 characters deliberately, so it cannot fire on a correctly
# redacted event: Intelligence's own digests are sha256 (64 hex), and the word
# boundary this pattern needs after 40 characters does not exist inside a
# 64-character hex run. Pseudonyms and path tokens carry `repository_` and
# `path_` prefixes and are likewise unaffected.
#
# Abbreviated ids (7-12 hex) are not matched: too many legitimate short tokens
# are hex, and a check that quarantined those would be turned off rather than
# fixed. This is a floor, not a proof of pseudonymity.
GIT_OBJECT_ID = re.compile(r"\b[0-9a-fA-F]{40}\b")
# Envelope fields that carry producer-supplied values. `payload` alone was
# inspected before, which is why a raw snapshot id sitting in
# `snapshot_or_run_id` -- one level up -- passed unexamined.
INSPECTED_EVENT_FIELDS = (
    "snapshot_or_run_id",
    "limitations",
    "unknowns",
    "lineage",
    "payload",
)


def inspect_value(
    value: Any,
    *,
    path: tuple[str, ...] = (),
) -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            if SENSITIVE_KEY.search(key_text):
                findings.append(f"sensitive-key:{'.'.join(path + (key_text,))}")
            findings.extend(
                inspect_value(
                    child,
                    path=path + (key_text,),
                )
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(
                inspect_value(
                    child,
                    path=path + (str(index),),
                )
            )
    elif isinstance(value, str):
        for pattern in SENSITIVE_VALUE_PATTERNS:
            if pattern.search(value):
                findings.append(f"sensitive-value:{'.'.join(path)}")
                break
        if ABSOLUTE_PATH.search(value):
            findings.append(f"absolute-path:{'.'.join(path)}")
        if GIT_OBJECT_ID.search(value):
            findings.append(f"git-object-id:{'.'.join(path)}")
    return findings


def assess_redaction(event: dict[str, Any]) -> RedactionAssessment:
    status = event.get("redaction_status")
    if status == "quarantine_required":
        return RedactionAssessment(
            safe=False,
            reason="redaction_required",
            limitations=("producer marked the event as requiring quarantine",),
        )
    findings: list[str] = []
    for field in INSPECTED_EVENT_FIELDS:
        if field in event:
            findings.extend(inspect_value(event[field], path=(field,)))
    findings = sorted(set(findings))
    if findings:
        return RedactionAssessment(
            safe=False,
            reason="sensitive_content",
            limitations=tuple(findings),
        )
    return RedactionAssessment(
        safe=True,
        reason=None,
        limitations=(),
    )
