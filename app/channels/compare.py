"""Constant-time secret checks. Empty configured secrets fail closed."""

import hashlib
import hmac


def constant_time_eq(left: str, right: str) -> bool:
    """Compare two strings by hashing them first so length differences do not short-circuit."""
    left_digest = hashlib.sha256(left.encode()).digest()
    right_digest = hashlib.sha256(right.encode()).digest()
    return hmac.compare_digest(left_digest, right_digest)


def secret_matches(provided: str, expected: str) -> bool:
    """True only when a non-empty expected secret matches `provided`."""
    if not expected:
        return False
    return constant_time_eq(provided, expected)


def header_value(headers: object, name: str) -> str:
    """Read one header, ignoring case. Missing headers are empty strings."""
    if not isinstance(headers, dict):
        return ""
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted:
            return str(value)
    return ""
