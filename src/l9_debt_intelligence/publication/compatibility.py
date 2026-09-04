from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .errors import PublicationGateError

# NOTE: the separator is a single escaped dot. In a raw string ``\\.`` is two
# characters -- backslash, backslash -- which compiles to a regex matching a
# LITERAL BACKSLASH followed by any character. That is what this pattern used to
# say, so parse_version() rejected every ordinary semantic version and accepted
# only nonsense like ``1\.0\.0``. Assembling a defense pack was impossible: both
# assemble_pack() and load_compatibility() call parse_version on their way in.
VERSION = re.compile(
    r"^(?P<major>0|[1-9][0-9]*)\."
    r"(?P<minor>0|[1-9][0-9]*)\."
    r"(?P<patch>0|[1-9][0-9]*)"
    r"(?:-[A-Za-z0-9.-]+)?$"
)


def parse_version(value: str) -> tuple[int, int, int]:
    match = VERSION.match(value)
    if match is None:
        raise PublicationGateError(f"invalid semantic version: {value}")
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
    )


def load_compatibility(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PublicationGateError("compatibility matrix must be a JSON object")
    if value.get("schema_version") != ("l9.defense-compatibility/v1"):
        raise PublicationGateError("unsupported compatibility matrix schema")
    sdk = value.get("sdk")
    if not isinstance(sdk, dict):
        raise PublicationGateError("compatibility matrix has no SDK section")
    minimum = parse_version(str(sdk["minimum_version"]))
    maximum = parse_version(str(sdk["maximum_version_exclusive"]))
    if minimum >= maximum:
        raise PublicationGateError("SDK minimum version must be lower than maximum")
    platforms = value.get("platforms")
    if not isinstance(platforms, list) or not platforms:
        raise PublicationGateError("compatibility matrix must define platforms")
    return value
