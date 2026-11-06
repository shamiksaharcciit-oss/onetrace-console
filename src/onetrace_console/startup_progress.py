"""What the console is doing while it starts: one line per phase on stderr, with counts and times.

`onetrace-console demo` records the demo's runs, loads and checks them, compares the pairs and draws
the pages before it prints an address; on a first start that takes minutes, and silence reads as a hang.
Now each phase says itself as it happens, flushed: `recording the demo's runs: 9 pipelines … 41 runs,
38 s`; `checking runs: 12 of 41`; `comparing pairs: 4 of 9`; `drawing pages: 520 of 1800`; then the
address. On a terminal a count line updates in place (`\\r`); where stderr is not a terminal (CI, a log
file) each step is a line of its own. The first line is said at once. `--quiet` keeps the old silence.

The phases are said by the code that does them (`phase`), through the one `Progress` the command set up
(`using`); with none set up -- a library caller, a test, `serve` -- they say nothing.
"""
from __future__ import annotations

import contextlib
import sys
import time


class Progress:
    """Phase lines to `stream`: in place on a terminal (`tty`), one line per step otherwise."""

    def __init__(self, stream=None, *, tty: bool | None = None, clock=time.monotonic):
        self.stream = sys.stderr if stream is None else stream
        if tty is None:
            try:
                tty = bool(self.stream.isatty())
            except (AttributeError, ValueError, OSError):
                tty = False
        self.tty, self.clock = tty, clock
        self._open = False             # a count line is on the terminal, not yet ended

    def _write(self, text: str) -> None:
        try:
            self.stream.write(text)
            self.stream.flush()
        except (OSError, ValueError):
            pass                       # a closed or broken stderr never stops the console starting

    def say(self, line: str) -> None:
        """One line of its own, ending any count line on the terminal first."""
        self._end_line()
        self._write(line + "\n")

    def _end_line(self) -> None:
        if self._open:
            self._write("\n")
            self._open = False

    def _count(self, line: str) -> None:
        if self.tty:
            self._write("\r" + line + "\x1b[K")
            self._open = True
        else:
            self._write(line + "\n")

    @contextlib.contextmanager
    def phase(self, name: str, total: int, *, done=None):
        """`with progress.phase("checking runs", 41) as step:` -- `step()` after each one; the phase
        ends with its count and the seconds it took. `done(n, seconds)`, where given, words the last
        line instead."""
        started = self.clock()
        count = [0]
        self._count(f"{name}: 0 of {total}")

        def step(n: int = 1) -> None:
            count[0] += n
            self._count(f"{name}: {count[0]} of {total}")
        try:
            yield step
        finally:
            took = self.clock() - started
            last = done(count[0], took) if done else f"{name}: {count[0]} of {total}, {seconds(took)}"
            if self.tty:
                self._write("\r" + last + "\x1b[K\n")
                self._open = False
            else:
                self._write(last + "\n")


def seconds(took: float) -> str:
    """A phase's time as it is said: whole seconds, or under a second."""
    return "under 1 s" if took < 1 else f"{round(took)} s"


class _Silent:
    """No progress set up: every phase says nothing."""

    def say(self, line: str) -> None:
        pass

    @contextlib.contextmanager
    def phase(self, name: str, total: int, *, done=None):
        yield lambda n=1: None


_SILENT = _Silent()
_CURRENT: list = [_SILENT]


def current():
    return _CURRENT[-1]


@contextlib.contextmanager
def using(progress):
    """`with using(Progress()):` -- the phases said inside go to it."""
    _CURRENT.append(progress)
    try:
        yield progress
    finally:
        _CURRENT.pop()


def phase(name: str, total: int, *, done=None):
    return current().phase(name, total, done=done)


def say(line: str) -> None:
    current().say(line)


FIRST_DEMO = ("starting: the first start records and checks the demo's runs; this takes a few minutes. "
              "Later starts reuse them.")
LATER_DEMO = "starting: reusing the demo's runs in {folder}/; this is quicker than the first start."
FOLDER = "starting: loading the runs in {folder}"
