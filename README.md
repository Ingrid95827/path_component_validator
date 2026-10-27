# path_component_validator

Validates that each segment of a path conforms to OS-specific rules for length, reserved names, illegal characters, and case folding before filesystem operations.

## Usage

```python
from path_component_validator import (
    Os,
    validate_path,
)

report = validate_path(["documents", "CON", "notes.txt"], target_os=Os.WINDOWS)
if not report.valid:
    for v in report.violations:
        print(f"{v.component!r}: {v.rule} — {v.reason}")
else:
    print("all segments are valid")
```

## Why this exists

A path built from user input can fail at filesystem-creation time for reasons that are entirely predictable: the segment is too long, it contains a character the OS forbids, or it collides with a reserved device name like `CON` on Windows. Catching these before the `open()` call turns a runtime `OSError` into a plain validation failure the caller can present to the user.

The trade-off is conservatism. The validators do not attempt to be a complete reimplementation of every filesystem's rules — they enforce the common, documented constraints of Windows (NTFS / FAT family) and POSIX (ext4, APFS, UFS, etc.). Anything that might be illegal is rejected; the caller is expected to handle the rejection.

## What the validators check

Each segment is tested independently and in order:

- **Empty segments** are rejected on every platform (they usually indicate a malformed path with a doubled separator).
- **Length**: segments longer than 255 characters are rejected. This is the NTFS limit and a common POSIX limit; some filesystems allow more, but 255 is the safe portable bound.
- **Illegal characters**:
  - Windows: `< > : " / \ \\ | ? *`
  - POSIX: the NUL byte and the forward slash `/`.
- **Reserved names**: Windows reserves `CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, and `LPT1`–`LPT9`. Matching is case-insensitive and ignores any file extension, so `con.txt` and `CON.` are both rejected. POSIX has no reserved names.
- **Case**: neither validator rejects a segment for its case alone. Windows is case-insensitive but case-preserving; POSIX is case-sensitive. Whether two segments that differ only in case collide is a concern for the caller (e.g. when checking for overwrites), not something the validator can judge in isolation.

## Awkward edges

- **`.` and `..` on POSIX**: these are not illegal — they are valid directory entries — but a segment that is exactly `.` or `..` almost always indicates a bug in the caller's path handling. The POSIX validator flags them with the rule `dot_directory`; treat this as a warning, not a hard error.
- **Unicode and normalisation**: the validators do not perform Unicode normalisation. Two strings that look identical but have different decompositions will be judged independently. If you need normalised comparison, apply `unicodedata.normalize` before calling `validate_path`.
- **The caller splits the path**: `validate_path` takes a list of segments, not a full path string. Splitting is the caller's responsibility so that the behaviour is explicit and the validator never has to guess at separator semantics.
- **No path separator in a segment**: the validators assume each element of the list is a single segment. If a segment contains a `/` on POSIX it will be rejected (as an illegal character), which is the intended behaviour — the caller should have split first.

## Exported names

- `Os` — enum with members `Os.WINDOWS` (value `"windows"`) and `Os.POSIX` (value `"posix"`).
- `Violation` — frozen dataclass with fields `component: str`, `rule: str`, `reason: str`.
- `ValidationReport` — frozen dataclass with field `violations: list[Violation]` and property `valid: bool`.
- `WindowsValidator`, `PosixValidator` — validator classes. Each has a `MAX_LENGTH` class attribute, an `ILLEGAL_CHARS` frozenset, and a `validate(components: list[str]) -> ValidationReport` method.
- `VALIDATORS` — dict mapping `Os` members (and their string values) to validator instances.
- `validate_path(components, target_os=Os.POSIX) -> ValidationReport` — convenience entry point. `target_os` accepts an `Os` member or the equivalent string.

## Running the tests

```
PYTHONPATH=src python -m unittest discover -s tests
```

## Performance

The window keeps a bounded buffer, so `push` is constant time and memory does not
grow with the length of the stream. `peak` and `trough` are linear in the window
size, which is the trade that keeps `push` cheap.

## Design notes

The window stores values eagerly rather than keeping running aggregates. Running
sums drift with floating point over long streams, and recomputing from a small
buffer is cheap enough that the drift is not worth the speed.

