#!/usr/bin/env python3
"""Fail when tracked source files contain likely credentials.

The scanner deliberately reports only file, line, and credential kind. It
never prints the suspected value into CI logs.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKIP_SUFFIXES = {
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".lock",
    ".onnx",
    ".pdf",
    ".png",
    ".pyc",
    ".wav",
    ".webp",
}

STRONG_PATTERNS = {
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "private key": re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"),
}

ASSIGNMENT = re.compile(
    r"""(?x)
    (?P<name>[A-Z][A-Z0-9_]*(?:API_KEY|KEY|TOKEN|SECRET|PASSWORD|COOKIE|DSN)[A-Z0-9_]*)
    \s*[:=]\s*
    ["']?(?P<value>[^\s"',}#]+)
    """
)

SAFE_VALUE_PREFIXES = (
    "$",
    "[",
    "<",
    "dummy",
    "example",
    "fake",
    "import.meta.",
    "os.",
    "placeholder",
    "test-",
    "your_",
)


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [
        ROOT / item.decode("utf-8")
        for item in result.stdout.split(b"\0")
        if item
    ]


def is_safe_assignment(value: str) -> bool:
    normalized = value.strip().casefold()
    return (
        not normalized
        or normalized in {"none", "null"}
        or normalized.startswith(SAFE_VALUE_PREFIXES)
    )


def scan_file(path: Path) -> list[tuple[int, str]]:
    if path.suffix.casefold() in SKIP_SUFFIXES:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    findings: list[tuple[int, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for label, pattern in STRONG_PATTERNS.items():
            if pattern.search(line):
                findings.append((line_number, label))
        for match in ASSIGNMENT.finditer(line):
            if match.group("name").endswith("_STORAGE_KEY"):
                continue
            value = match.group("value")
            if len(value) >= 12 and not is_safe_assignment(value):
                findings.append(
                    (line_number, f"non-placeholder {match.group('name')}")
                )
    return findings


def main() -> int:
    findings = [
        (path.relative_to(ROOT), line_number, label)
        for path in tracked_files()
        for line_number, label in scan_file(path)
    ]
    if not findings:
        print("Secret scan passed: no likely credentials in tracked files.")
        return 0

    print("Secret scan failed. Suspected values were suppressed:", file=sys.stderr)
    for path, line_number, label in findings:
        print(f"  {path}:{line_number}: {label}", file=sys.stderr)
    print(
        "Remove the value, rotate it at the provider, and store it in a local .env.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
