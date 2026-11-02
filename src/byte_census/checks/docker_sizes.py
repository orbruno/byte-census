"""Parsing of Docker's human-readable figures (quantities.md, Docker figures).

Sizes use Docker's decimal base: 1 kB = 1,000 bytes, 1 GB = 1,000,000,000.
The conversion is exact integer arithmetic (half up), so `7.42GB` is always
7,420,000,000. A string that is not a size gives `None`; callers keep the raw
string beside the number so the conversion stays auditable.
"""

import re
from datetime import datetime

from byte_census.model import format_captured_at

UNITS = {
    "B": 1,
    "KB": 1_000,
    "MB": 1_000_000,
    "GB": 1_000_000_000,
    "TB": 1_000_000_000_000,
    "PB": 1_000_000_000_000_000,
}
SIZE = re.compile(r"^(\d+)(?:\.(\d+))?\s*([kKMGTP]?B)$")
CREATED = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) ([+-]\d{4})\b")


def parse_docker_size(raw: str) -> int | None:
    """Bytes for a Docker size string such as `7.42GB`, else `None`."""
    match = SIZE.match(raw.strip())
    if match is None:
        return None
    whole, fraction, unit = match.groups()
    scale = UNITS[unit.upper()]
    digits = fraction or ""
    numerator = int(whole + digits) * scale
    denominator = 10 ** len(digits)
    return (2 * numerator + denominator) // (2 * denominator)


def parse_reclaimable(raw: str) -> int | None:
    """Bytes for `3.18GB (42%)`; the percentage is Docker's own ratio."""
    return parse_docker_size(raw.split("(", 1)[0])


def docker_created_at(raw: str) -> str:
    """RFC 3339 UTC for `2026-06-02 15:40:03 +0000 UTC`, else the raw text."""
    match = CREATED.match(raw.strip())
    if match is None:
        return raw
    day, clock, offset = match.groups()
    moment = datetime.strptime(f"{day} {clock} {offset}", "%Y-%m-%d %H:%M:%S %z")
    return format_captured_at(moment)
