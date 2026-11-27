# SPDX-FileCopyrightText: 2026 Thomas Frey
#
# SPDX-License-Identifier: BSD-3-Clause

# ABOUTME: The `command` shell builtin: `command -v NAME` says how a name would
# ABOUTME: be run, `command NAME ARGS` runs it past any shell function.

from __future__ import annotations

from cowrie.shell.command import HoneyPotCommand
from cowrie.shell.pipe import BASH_BUILTINS, PipeProtocol

commands = {}

# Words bash reports as "a shell keyword".
KEYWORDS = frozenset(
    "! [[ ]] case coproc do done elif else esac fi for function if in select "
    "then time until while { }".split()
)

USAGE = "command: usage: command [-pVv] command [arg ...]\n"


class Command_command(HoneyPotCommand):
    """``command [-pVv] NAME [ARG ...]``.

    Loader scripts ask ``command -v wget`` before they pick a download tool.
    With ``-v`` the builtin prints what each name resolves to and fails when
    none of them is known; with ``-V`` it says so in words. Without either it
    runs NAME in its own place, ignoring shell functions of that name.
    """

    consumes_stdin = True

    def start(self) -> None:
        args = list(self.args)
        mode = ""
        while args and args[0].startswith("-") and len(args[0]) > 1:
            option = args.pop(0)
            if option == "--":
                break
            for flag in option[1:]:
                if flag in "vV":
                    mode = flag
                elif flag != "p":
                    self.errorWrite(
                        f"{self.shell.error_prefix()}command: -{flag}: invalid option\n"
                    )
                    self.errorWrite(USAGE)
                    self.exit(2)
                    return

        if not args:
            self.exit(0)
            return
        if mode:
            self.describe(args, verbose=mode == "V")
            return
        self.run(args)

    def lookup(self, name: str) -> tuple[str, str] | None:
        """What NAME resolves to, as (kind, path), or None when unknown."""
        if name in KEYWORDS:
            return "keyword", name
        if name in self.shell.functions:
            return "function", name
        if name in BASH_BUILTINS:
            return "builtin", name
        if "/" in name:
            path = self.fs.resolve_path(name, self.cwd)
            return ("file", name) if self.fs.isfile(path) else None
        for directory in self.environ.get("PATH", "").split(":"):
            if directory and self.fs.isfile(self.fs.resolve_path(name, directory)):
                return "file", f"{directory.rstrip('/')}/{name}"
        # A command the honeypot emulates without a file on PATH still runs,
        # so it is reported where it is registered.
        if name in self.protocol.commands:
            for registered in sorted(self.protocol.commands):
                if registered.endswith(f"/{name}"):
                    return "file", registered
        return None

    def describe(self, names: list[str], *, verbose: bool) -> None:
        found = False
        for name in names:
            hit = self.lookup(name)
            if hit is None:
                if verbose:
                    self.errorWrite(
                        f"{self.shell.error_prefix()}command: {name}: not found\n"
                    )
                continue
            found = True
            kind, path = hit
            if not verbose:
                self.write(f"{path}\n")
            elif kind == "keyword":
                self.write(f"{name} is a shell keyword\n")
            elif kind == "function":
                self.write(f"{name} is a function\n")
            elif kind == "builtin":
                self.write(f"{name} is a shell builtin\n")
            else:
                self.write(f"{name} is {path}\n")
        self.exit(0 if found else 1)

    def run(self, args: list[str]) -> None:
        cmd = args[0]
        cmdclass = self.protocol.getCommand(
            cmd, self.environ.get("PATH", "").split(":"), self.cwd
        )
        if not cmdclass:
            self.protocol.events.dispatch(
                "cowrie.command.failed",
                "Command not found: %(input)s",
                input=" ".join(args),
            )
            self.errorWrite(self.shell.command_not_found_message(cmd))
            self.exit(127)
            return

        pp = PipeProtocol(
            self.protocol,
            cmdclass,
            args[1:],
            self.input_data,
            self.pp.targets,
            cwd=self.cwd,
            user=self.user,
        )
        pp.stdin_from_pipe = self.pp.stdin_from_pipe
        pp.argv0 = cmd
        self.exec_command(pp, cmdclass, *args[1:])


commands["command"] = Command_command
