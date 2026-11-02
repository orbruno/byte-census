"""Shared rich consoles for the legacy dupfind command."""

from rich.console import Console

console = Console()
status_console = Console(stderr=True)
