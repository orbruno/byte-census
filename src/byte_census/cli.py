"""byte-census command group.

`ByteCensusGroup.main` is the single error path: every failure becomes the
JSON error object on stderr with exit code 1, 2, 3, or 4, and stdout stays
empty. Click usage errors are converted to the same shape. `invoke` converts
errors that Click raises without a context (a missing option value) and
interruptions before Click sees them, so the help hint names the subcommand
and stderr holds exactly one JSON object. Nothing prompts.
"""

import sys
from typing import Any

import click

from byte_census import __version__
from byte_census.checks.artifacts import artifacts
from byte_census.checks.docker import docker
from byte_census.errors import (
    TOOL_HELP,
    emit_error,
    to_byte_census_error,
    usage_error,
)
from byte_census.selftest import selftest


def _subcommand_path(ctx: click.Context) -> str:
    if ctx.invoked_subcommand is None:
        return ctx.command_path
    return f"{ctx.command_path} {ctx.invoked_subcommand}"


class ByteCensusGroup(click.Group):
    """Click group whose standalone mode reports errors as JSON."""

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except click.UsageError as error:
            if error.ctx is not None:
                raise
            path = _subcommand_path(ctx)
            raise usage_error(path, error.format_message()) from error
        except (click.Abort, KeyboardInterrupt) as error:
            help_hint = f"{_subcommand_path(ctx)} --help"
            raise to_byte_census_error(error).with_help(help_hint) from error

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
main.add_command(docker)
main.add_command(artifacts)


if __name__ == "__main__":
    main()
