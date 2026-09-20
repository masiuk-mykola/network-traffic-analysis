import argparse
import importlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass

type Configure = Callable[[argparse.ArgumentParser], None]
type Run = Callable[[argparse.Namespace], int]


def _no_arguments(_parser: argparse.ArgumentParser) -> None:
    return None


@dataclass(frozen=True, slots=True)
class Command:
    name: str
    help: str
    configure: Configure
    run: Run


COMMANDS: dict[str, Command] = {}


def register(cmd: Command) -> Command:
    existing = COMMANDS.get(cmd.name)
    if existing is not None and existing.run is not cmd.run:
        raise ValueError(f"CLI command {cmd.name!r} registered twice")
    COMMANDS[cmd.name] = cmd
    return cmd


def command(name: str, *, help: str, configure: Configure = _no_arguments) -> Callable[[Run], Run]:

    def decorator(run: Run) -> Run:
        register(Command(name=name, help=help, configure=configure, run=run))
        return run

    return decorator


def discover() -> dict[str, Command]:
    for info in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{__name__}.{info.name}")
    return dict(sorted(COMMANDS.items()))
