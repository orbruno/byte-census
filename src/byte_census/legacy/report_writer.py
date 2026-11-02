"""Report file writer for the legacy dupfind command.

This is the only module that writes files.
"""

import errno
import os
from pathlib import Path

import click

from byte_census.legacy.consoles import status_console

EXISTING_OUTPUT_EXIT_CODE = 3
_CREATE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW


class ExistingOutputError(click.ClickException):
    """Raised when the output path already exists; exits with code 3."""

    exit_code = EXISTING_OUTPUT_EXIT_CODE

    def __init__(self, output: Path) -> None:
        super().__init__(
            f"Output file already exists: {output}. "
            "Choose a new path or remove the existing file first."
        )


def write_report(output: Path, text: str | None) -> None:
    """Create the output file exclusively and write the report text to it.

    An existing file or a symlink (dangling or not) exits 3 without writing.
    """
    try:
        descriptor = os.open(output, _CREATE_FLAGS, 0o666)
    except FileExistsError as error:
        raise ExistingOutputError(output) from error
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise ExistingOutputError(output) from error
        raise _cannot_write(output, error) from error
    try:
        _write_text(descriptor, text or "")
    except Exception as error:
        _remove_created_file(output, descriptor)
        raise _cannot_write(output, error) from error
    finally:
        os.close(descriptor)
    status_console.print(f"✓ Results saved to {output}", style="green", markup=False)


def _write_text(descriptor: int, text: str) -> None:
    """Write text as UTF-8, keeping undecodable path bytes (surrogateescape)."""
    data = memoryview(text.encode("utf-8", errors="surrogateescape"))
    while data:
        data = data[os.write(descriptor, data) :]


def _remove_created_file(output: Path, descriptor: int) -> None:
    """Unlink output only if it is still the file this writer created."""
    try:
        created = os.fstat(descriptor)
        current = os.lstat(output)
        if (created.st_dev, created.st_ino) == (current.st_dev, current.st_ino):
            os.unlink(output)
    except OSError:
        pass


def _cannot_write(output: Path, error: Exception) -> click.ClickException:
    return click.ClickException(f"Cannot write output file {output}: {error}")
