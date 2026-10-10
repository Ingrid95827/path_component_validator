# SPDX-License-Identifier: MIT
"""Core validation logic for path components.

Each segment of a filesystem path is subject to rules that differ between
operating systems. A segment may be too long, contain characters that are
reserved on some platforms (but harmless on others), collide with a reserved
device name, or violate case conventions.

The validators here are deliberately conservative: they reject anything that
*could* be illegal on the target platform. When in doubt, a segment is rejected
and the caller must decide how to present that. The validators never mutate the
input or normalise it — they only judge it.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import List


class Os(str, Enum):
    """Target filesystem family.

    Members are strings so callers can pass plain values
    (``Os.WINDOWS`` or ``"windows"``) interchangeably.
    """

    WINDOWS = "windows"
    POSIX = "posix"


@dataclass(frozen=True)
class Violation:
    """A single rule that a path component failed.

    Attributes:
        component: The segment (never mutated).
        rule: Identifier of the rule that failed (e.g. "reserved_name").
        reason: Human-readable explanation of the failure.
    """

    component: str
    rule: str
    reason: str


@dataclass(frozen=True)
class ValidationReport:
    """Result of validating one or more path components.

    ``valid`` is derived from ``violations``: an empty list means valid.
    Components are reported in the same order they were supplied, and each
    component's violations are grouped together.
    """

    violations: List[Violation] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.violations


class _BaseValidator:
    """Common helpers shared by platform-specific validators.

    Subclasses define:
        MAX_LENGTH
        ILLEGAL_CHARS
        reserved_names() -> frozenset[str]
        case_violations(component) -> list[Violation]
    """

    MAX_LENGTH: int
    ILLEGAL_CHARS: frozenset[str]

    def validate(self, components: List[str]) -> ValidationReport:
        violations: List[Violation] = []
        for component in components:
            violations.extend(self._validate_one(component))
        return ValidationReport(violations=violations)

    def _validate_one(self, component: str) -> List[Violation]:
        out: List[Violation] = []

        if not isinstance(component, str):
            raise TypeError(
                f"path component must be str, got {type(component).__name__}"
            )

        if component == "":
            # An empty segment usually indicates a malformed path (e.g. a
            # double separator). Treat that as an error rather than silently
            # accepting it.
            out.append(
                Violation(
                    component=component,
                    rule="empty",
                    reason="path segment is empty",
                )
            )
            return out

        if len(component) > self.MAX_LENGTH:
            out.append(
                Violation(
                    component=component,
                    rule="too_long",
                    reason=(
                        f"segment length {len(component)} exceeds "
                        f"maximum {self.MAX_LENGTH}"
                    ),
                )
            )

        for ch in component:
            if ch in self.ILLEGAL_CHARS:
                out.append(
                    Violation(
                        component=component,
                        rule="illegal_char",
                        reason=(
                            f"segment contains illegal character "
                            f"U+{ord(ch):04X}"
                        ),
                    )
                )
                # One report per character is enough; duplicates would just
                # spam the caller.
                break

        out.extend(self._check_reserved(component))
        out.extend(self._check_case(component))
        return out

    def _check_reserved(self, component: str) -> List[Violation]:
        # Strip a trailing dot so that "CON." is treated the same as "CON";
        # Windows resolves both to the device.
        stem = component.rstrip(".")
        match = re.match(r"^([^.]+)", stem)
        if not match:
            return []
        base = match.group(1).upper()
        if base in self.reserved_names():
            return [
                Violation(
                    component=component,
                    rule="reserved_name",
                    reason=(
                        f"segment matches reserved name '{base}' "
                        "(case-insensitive, extension ignored)"
                    ),
                )
            ]
        return []

    def reserved_names(self) -> frozenset[str]:
        raise NotImplementedError

    def _check_case(self, component: str) -> List[Violation]:
        raise NotImplementedError


class WindowsValidator(_BaseValidator):
    """Validator for Windows NTFS / FAT family rules.

    Windows has the strictest rules of mainstream filesystems: a fixed set of
    illegal characters, a length limit, and a list of reserved device names
    that cannot be used as filenames regardless of extension.
    """

    MAX_LENGTH = 255
    ILLEGAL_CHARS = frozenset('<>:"/\\|?*')

    _RESERVED_NAMES = frozenset(
        {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            "COM1",
            "COM2",
            "COM3",
            "COM4",
            "COM5",
            "COM6",
            "COM7",
            "COM8",
            "COM9",
            "LPT1",
            "LPT2",
            "LPT3",
            "LPT4",
            "LPT5",
            "LPT6",
            "LPT7",
            "LPT8",
            "LPT9",
        }
    )

    def reserved_names(self) -> frozenset[str]:
        return self._RESERVED_NAMES

    def _check_case(self, component: str) -> List[Violation]:
        # Windows is case-insensitive but case-preserving. There is no
        # "illegal case" — we simply need to be aware that two segments
        # differing only in case collide. That is a concern for the caller
        # (e.g. when checking for overwrites), not something the validator
        # can judge in isolation, so we return no violations here.
        return []


class PosixValidator(_BaseValidator):
    """Validator for POSIX-family filesystems (ext4, APFS, UFS, etc.).

    POSIX is permissive: only the NUL byte and the path separator are
    forbidden. We go one step further and flag the conventional name for the
    current directory (``.``) and parent directory (``..``) as suspicious —
    not because they are illegal, but because a path component that is exactly
    one of these almost always indicates a bug in the caller's path handling.
    """

    MAX_LENGTH = 255
    ILLEGAL_CHARS = frozenset("\x00/")

    _DOTDIRS = frozenset({".", ".."})

    def reserved_names(self) -> frozenset[str]:
        return frozenset()

    def _check_case(self, component: str) -> List[Violation]:
        # POSIX is case-sensitive; there is nothing to flag here. The method
        # is kept for symmetry with WindowsValidator so that callers can treat
        # all validators uniformly.
        return []

    def _validate_one(self, component: str) -> List[Violation]:
        out = super()._validate_one(component)
        if component in self._DOTDIRS:
            out.append(
                Violation(
                    component=component,
                    rule="dot_directory",
                    reason=(
                        "segment is '.' or '..'; these are special and "
                        "should not appear as ordinary components"
                    ),
                )
            )
        return out


VALIDATORS = {
    Os.WINDOWS: WindowsValidator(),
    Os.POSIX: PosixValidator(),
    Os.WINDOWS.value: WindowsValidator(),
    Os.POSIX.value: PosixValidator(),
}


def validate_path(
    components: List[str],
    target_os: str | Os = Os.POSIX,
) -> ValidationReport:
    """Validate a list of path segments for the given target OS.

    Args:
        components: Path segments to validate. Each should be a single
            segment (no separators); callers are responsible for splitting
            a full path before calling this function.
        target_os: Either an :class:`Os` member or the equivalent string
            (``"windows"`` / ``"posix"``). Defaults to the host OS.

    Returns:
        A :class:`ValidationReport` whose ``violations`` list is in the
        same order as ``components``.

    Raises:
        TypeError: if any component is not a string.
        ValueError: if ``target_os`` is not recognised.
    """
    if isinstance(target_os, str) and not isinstance(target_os, Os):
        target_os = Os(target_os)
    elif not isinstance(target_os, Os):
        raise ValueError(f"unknown target OS: {target_os!r}")

    validator = VALIDATORS.get(target_os)
    if validator is None:
        raise ValueError(f"unknown target OS: {target_os!r}")

    return validator.validate(components)
