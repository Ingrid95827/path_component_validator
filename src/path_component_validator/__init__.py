# SPDX-License-Identifier: MIT
"""path_component_validator — validates individual path segments against filesystem rules."""

from .core import (
    Os,
    Violation,
    ValidationReport,
    WindowsValidator,
    PosixValidator,
    VALIDATORS,
    validate_path,
)

__all__ = [
    "Os",
    "Violation",
    "ValidationReport",
    "WindowsValidator",
    "PosixValidator",
    "VALIDATORS",
    "validate_path",
]

__version__ = "1.0.0"
