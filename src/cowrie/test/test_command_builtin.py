# SPDX-FileCopyrightText: 2026 Thomas Frey
#
# SPDX-License-Identifier: BSD-3-Clause

# ABOUTME: Tests for the `command` shell builtin: -v and -V say how a name
# ABOUTME: resolves, and without them the named command runs in its place.

from __future__ import annotations

import os
import tempfile
import unittest

from cowrie.shell.protocol import HoneyPotInteractiveProtocol
from cowrie.test.eventcapture import capture_events, events_of
from cowrie.test.fake_server import FakeAvatar, FakeServer
from cowrie.test.fake_transport import FakeTransport

os.environ["COWRIE_HONEYPOT_DATA_PATH"] = "data"
os.environ["COWRIE_HONEYPOT_DOWNLOAD_PATH"] = tempfile.gettempdir()
os.environ["COWRIE_SHELL_FILESYSTEM"] = "src/cowrie/data/fs.pickle"

PROMPT = b"root@unitTest:~# "


class CommandBuiltinTests(unittest.TestCase):
    def setUp(self) -> None:
        self.proto = HoneyPotInteractiveProtocol(FakeAvatar(FakeServer()))
        self.tr = FakeTransport("", "31337")
        self.proto.makeConnection(self.tr)
        self.tr.clear()
        self.events = capture_events(self.proto)

    def tearDown(self) -> None:
        self.proto.connectionLost()

    def run_line(self, line: bytes) -> bytes:
        self.tr.clear()
        self.proto.lineReceived(line)
        out: bytes = self.tr.value()
        return out[: -len(PROMPT)] if out.endswith(PROMPT) else out

    def test_v_prints_the_path_of_a_file_on_path(self) -> None:
        self.assertEqual(
            self.run_line(b"command -v wget; echo $?"), b"/usr/bin/wget\n0\n"
        )

    def test_v_is_silent_and_fails_for_an_unknown_name(self) -> None:
        self.assertEqual(self.run_line(b"command -v nosuchtool; echo $?"), b"1\n")
        self.assertEqual(events_of(self.events, "cowrie.command.failed"), [])

    def test_v_names_builtins_keywords_and_functions(self) -> None:
        self.run_line(b"f() { echo x; }")
        self.assertEqual(self.run_line(b"command -v echo if f"), b"echo\nif\nf\n")

    def test_v_succeeds_when_any_name_is_known(self) -> None:
        self.assertEqual(
            self.run_line(b"command -v nosuchtool ls; echo $?"), b"/usr/bin/ls\n0\n"
        )

    def test_v_with_a_path(self) -> None:
        self.assertEqual(self.run_line(b"command -v /bin/ls; echo $?"), b"/bin/ls\n0\n")
        self.assertEqual(self.run_line(b"command -v /bin/nope; echo $?"), b"1\n")
        self.assertEqual(self.run_line(b"command -v /bin; echo $?"), b"1\n")

    def test_loader_script_picks_the_tool_it_finds(self) -> None:
        # The shape droppers use to choose between wget, curl and busybox.
        out = self.run_line(
            b"if command -v nosuchtool >/dev/null 2>&1; then echo first; "
            b"elif command -v wget >/dev/null 2>&1; then echo second; fi"
        )
        self.assertEqual(out, b"second\n")

    def test_capital_v_describes_each_name(self) -> None:
        out = self.run_line(b"command -V ls echo if nosuchtool; echo $?")
        self.assertEqual(
            out,
            b"ls is /usr/bin/ls\necho is a shell builtin\nif is a shell keyword\n"
            b"-bash: command: nosuchtool: not found\n0\n",
        )

    def test_runs_the_named_command(self) -> None:
        self.assertEqual(self.run_line(b"command echo hi; echo $?"), b"hi\n0\n")
        self.assertEqual(self.run_line(b"command -p echo hi"), b"hi\n")

    def test_runs_the_command_not_the_function(self) -> None:
        self.run_line(b"echo() { printf 'function\\n'; }")
        self.assertEqual(self.run_line(b"command echo real"), b"real\n")

    def test_passes_exit_status_and_redirections(self) -> None:
        self.assertEqual(self.run_line(b"command false; echo $?"), b"1\n")
        self.assertEqual(
            self.run_line(b"command echo hi > /tmp/c; cat /tmp/c"), b"hi\n"
        )
        self.assertEqual(self.run_line(b"echo piped | command cat"), b"piped\n")

    def test_unknown_command_is_not_found(self) -> None:
        out = self.run_line(b"command nosuchtool arg; echo $?")
        self.assertEqual(out, b"-bash: nosuchtool: command not found\n127\n")
        failed = events_of(self.events, "cowrie.command.failed")
        self.assertEqual([e["input"] for e in failed], ["nosuchtool arg"])

    def test_without_a_name_does_nothing(self) -> None:
        self.assertEqual(self.run_line(b"command; echo $?"), b"0\n")
        self.assertEqual(self.run_line(b"command -v; echo $?"), b"0\n")

    def test_invalid_option(self) -> None:
        out = self.run_line(b"command -x ls; echo $?")
        self.assertEqual(
            out,
            b"-bash: command: -x: invalid option\n"
            b"command: usage: command [-pVv] command [arg ...]\n2\n",
        )


if __name__ == "__main__":
    unittest.main()
