"""byte-census command group.

`ByteCensusGroup.main` is the single error path: every failure becomes the
JSON error object on stderr with exit code 1, 2, 3, or 4, and stdout stays
empty. Click usage errors are converted to the same shape. Nothing prompts.
"""

import sys
from typing import Any

import click

from byte_census import __version__
from byte_census.errors import TOOL_HELP, emit_error, to_byte_census_error
from byte_census.selftest import selftest


class ByteCensusGroup(click.Group):
    """Click group whose standalone mode reports errors as JSON."""

    def main(self, *args: Any, standalone_mode: bool = True, **kwargs: Any) -> Any:
        if not standalone_mode:
            return super().main(*args, standalone_mode=False, **kwargs)
        try:
            rv = super().main(*args, standalone_mode=False, **kwargs)
        except Exception as error:  # noqa: BLE001 - every failure becomes JSON
            mapped = to_byte_census_error(error)
            emit_error(mapped.info(TOOL_HELP), sys.stderr)
            sys.exit(mapped.exit_code)
        sys.exit(rv if isinstance(rv, int) else 0)


@click.group(
    "byte-census",
    cls=ByteCensusGroup,
    context_settings={"help_option_names": ["--help", "-h"]},
    invoke_without_command=True,
)
@click.version_option(
    __version__, "--version", message="%(prog)s %(version)s", prog_name="byte-census"
)
@click.pass_context
def main(ctx: click.Context) -> None:
    """
    Census of the bytes on disk.

    Example:

      \b
      # Show the version
      byte-census --version
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


main.add_command(selftest)


if __name__ == "__main__":
    main()
