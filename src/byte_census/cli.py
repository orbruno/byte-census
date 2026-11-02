"""byte-census command group."""

import click

from byte_census import __version__


@click.group(
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


if __name__ == "__main__":
    main()
