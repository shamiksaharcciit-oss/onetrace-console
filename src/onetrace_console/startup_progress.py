"""What the console is doing while it starts: one line per phase on stderr, with counts and times.

`onetrace-console demo` records the demo's runs, loads and checks them, compares the pairs and draws
the pages before it prints an address; on a first start that takes minutes, and silence reads as a hang.
Now each phase says itself as it happens, flushed: `recording the demo's runs: 9 pipelines … 41 runs,
38 s`; `checking runs: 12 of 41`; `comparing pairs: 4 of 9`; `drawing pages: 520 of 1800`; then the
address. On a terminal a count line updates in place (`\\r`); where stderr is not a terminal (CI, a log
file) each step is a line of its own. On Windows the console's virtual-terminal mode is asked for before
the first line (`windows_vt`); where the console does not take it (Windows PowerShell 5.1's classic
console, say), a count line is redrawn with `\\r` and padded with spaces, and no escape code is written. The first line is said at once. `--quiet` keeps the old silence.

The phases are said by the code that does them (`phase`), through the one `Progress` the command set up
(`using`); with none set up -- a library caller, a test, `serve` -- they say nothing.
"""
from __future__ import annotations

import contextlib
import sys
import time


#: SetConsoleMode's flag for escape codes (`ESC[K`), as Windows names it.
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004


def windows_vt(stream) -> bool:
    """Whether the Windows console `stream` writes to takes escape codes, after asking it to
    (`SetConsoleMode` with ENABLE_VIRTUAL_TERMINAL_PROCESSING). False where it is no console, or
    refuses."""
    try:
        import ctypes
        import msvcrt
        handle = msvcrt.get_osfhandle(stream.fileno())
        kernel32 = ctypes.windll.kernel32
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if mode.value & ENABLE_VIRTUAL_TERMINAL_PROCESSING:
            return True
        return bool(kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING))
    except Exception:  # noqa: BLE001 - any way it is not taken, the lines are drawn without escape codes
        return False


class Progress:
    """Phase lines to `stream`: in place on a terminal (`tty`), one line per step otherwise. `vt`:
    whether the terminal takes escape codes; by default, yes, but on Windows only where its console
    takes virtual-terminal mode when asked (a stream with no file behind it is taken at its word)."""

    def __init__(self, stream=None, *, tty: bool | None = None, vt: bool | None = None, clock=time.monotonic):
        self.stream = sys.stderr if stream is None else stream
        if tty is None:
            try:
                tty = bool(self.stream.isatty())
            except (AttributeError, ValueError, OSError):
                tty = False
        if tty and vt is None:
            vt = True
            if sys.platform == "win32":
                try:
                    self.stream.fileno()
                except (AttributeError, ValueError, OSError):
                    pass               # no file behind it: a caller's stream, taken at its word
                else:
                    vt = windows_vt(self.stream)
        self.tty, self.vt, self.clock = tty, bool(vt), clock
        self._open = False             # a count line is on the terminal, not yet ended
        self._width = 0                # the count line's length on the terminal, where no escape erases it

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
            self._width = 0

    def _in_place(self, line: str, end: str = "") -> None:
        """`line` over the count line on the terminal: erased by escape code, or padded with spaces."""
        if self.vt:
            self._write("\r" + line + "\x1b[K" + end)
        else:
            self._write("\r" + line + " " * max(0, self._width - len(line)) + end)
        self._width = 0 if end else len(line)

    def _count(self, line: str) -> None:
        if self.tty:
            self._in_place(line)
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
                self._in_place(last, "\n")
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
