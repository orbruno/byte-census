"""Validation of scan-root arguments (WI-SAFETY AC-06).

`validate_root` is pure apart from one `stat` call. WI-CORE maps
`PathValidationError` to exit code 3 (`validation_error`).
"""

import os
import stat
import unicodedata
from pathlib import Path


class PathValidationError(ValueError):
    """A path argument failed validation; `reason` names the rule."""

    def __init__(self, path: str, reason: str, message: str) -> None:
        super().__init__(message)
        self.path = path
        self.reason = reason


def _check_characters(text: str) -> None:
    if text == "":
        raise PathValidationError(text, "empty", "path is empty")
    if "\x00" in text:
        raise PathValidationError(
            text, "null_byte", f"path contains a null byte: {text!r}"
        )
    if any(unicodedata.category(char) == "Cc" for char in text):
        raise PathValidationError(
            text, "control_character", f"path contains a control character: {text!r}"
        )


def validate_root(path: str | os.PathLike[str]) -> Path:
    """Return the resolved scan root, or raise PathValidationError.

    Rejects empty paths, null bytes, and control characters (Unicode category
    Cc: C0, DEL, and C1), then requires an existing directory. A symlinked
    root is resolved once with realpath.
    """
    if not isinstance(path, (str, os.PathLike)):
        raise PathValidationError(repr(path), "invalid_type", "path must be a string")
    text = os.fspath(path)
    if not isinstance(text, str):
        raise PathValidationError(repr(text), "invalid_type", "path must be a string")
    _check_characters(text)
    try:
        info = os.stat(text)
    except FileNotFoundError as error:
        raise PathValidationError(
            text, "not_found", f"path does not exist: {text}"
        ) from error
    except OSError as error:
        raise PathValidationError(
            text, "inaccessible", f"path cannot be read: {text}: {error.strerror}"
        ) from error
    if not stat.S_ISDIR(info.st_mode):
        raise PathValidationError(
            text, "not_a_directory", f"path is not a directory: {text}"
        )
    return Path(os.path.realpath(text))
