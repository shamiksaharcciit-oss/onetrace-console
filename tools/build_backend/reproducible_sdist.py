"""The console's build backend: setuptools' own, with the sdist written again so that two builds of
one commit are the same bytes.

setuptools gives each member of the sdist its file's time, and the gzip header the time of the
build, so two builds from two checkouts of one commit differed in those times alone. Where
SOURCE_DATE_EPOCH is set, as a release build sets it to the commit's time, `build_sdist` writes the
same members again, in the same order with the same bytes and modes: every member's time that
epoch, no owner, and the gzip header's time that epoch too. Without it the sdist is setuptools'
as it was. The wheel is setuptools' own; it already takes its times from SOURCE_DATE_EPOCH.

The same bytes on Windows as on Linux: what setuptools writes differs there in three ways, and the
backend writes each as Linux gives it, in the sdist (when it writes it again) and in the wheel (only
where a member differs, so a Linux build's wheel is setuptools' own bytes):
- a member's mode, from the file's: Windows gives 0666 for a file and 0777 for a folder; each is 0644,
  or 0755 where its owner may run it, and a folder 0755 (the wheel's RECORD keeps the mode setuptools
  gives it on every platform);
- the text setuptools writes in text mode -- PKG-INFO, setup.cfg, and the wheel's METADATA -- has CRLF
  there; it is LF, and the wheel's RECORD line for METADATA is its hash and size then;
- each wheel member's creating system: Python's zipfile names MS-DOS on Windows; it is Unix.

pyproject.toml names this module (`backend-path`), and MANIFEST.in carries it into the sdist, so
a wheel builds from the sdist by the same backend.
"""
from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import io
import os
import stat
import tarfile
import zipfile
from pathlib import Path

from setuptools import build_meta as _setuptools
from setuptools.build_meta import *  # noqa: F401,F403  (every hook setuptools gives, unchanged)

#: The PAX fields that carry a time or an owner; the epoch and the plain fields stand for them.
_PAX_DROPPED = ("mtime", "atime", "ctime", "uid", "gid", "uname", "gname")
#: The text setuptools writes in text mode (CRLF on Windows), by a member's last part.
_TEXT_MODE = ("PKG-INFO", "setup.cfg", "METADATA")
#: The creating system zipfile names on Linux and macOS, as the wheel gives it there.
_UNIX = 3


def _mode(mode: int, folder: bool) -> int:
    """A member's permission bits as Linux gives them: a folder 0755; a file 0755 where its owner may run
    it, else 0644."""
    return 0o755 if folder or mode & stat.S_IXUSR else 0o644


def _text(name: str, data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n") if name.rsplit("/", 1)[-1] in _TEXT_MODE else data


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    name = _setuptools.build_wheel(wheel_directory, config_settings, metadata_directory)
    as_linux(Path(wheel_directory) / name)
    return name


def as_linux(path: Path) -> bool:
    """The wheel at `path` written again where any member differs from what Linux gives (its mode, its
    creating system, or CRLF in METADATA), each member as Linux gives it, in the same order, with the
    same times and compression; RECORD's line for a member written again its hash and size then. Untouched
    where nothing differs. Whether it was written again."""
    with zipfile.ZipFile(path) as z:
        infos = [(i, z.read(i)) for i in z.infolist()]
    record = next((i.filename for i, _ in infos if i.filename.endswith(".dist-info/RECORD")), None)

    def plain(i: zipfile.ZipInfo, data: bytes) -> bool:
        mode = i.external_attr >> 16
        return (i.create_system == _UNIX and _text(i.filename, data) == data
                and (i.filename == record or stat.S_IMODE(mode) == _mode(mode, i.is_dir())))
    if all(plain(i, data) for i, data in infos):
        return False
    changed: dict[str, bytes] = {}
    out = []
    for i, data in infos:
        new = _text(i.filename, data)
        if new != data:
            changed[i.filename] = new
        n = zipfile.ZipInfo(i.filename, i.date_time)
        n.compress_type, n.create_system = i.compress_type, _UNIX
        mode = i.external_attr >> 16
        n.external_attr = (mode if i.filename == record
                           else stat.S_IFMT(mode) | _mode(mode, i.is_dir())) << 16 | (i.external_attr & 0xFFFF)
        out.append((n, new))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        for n, data in out:
            if n.filename == record and changed:
                data = _record(data, changed)
            z.writestr(n, data)
    return True


def _record(data: bytes, changed: dict[str, bytes]) -> bytes:
    """RECORD with each changed member's line its new hash and size, as setuptools writes RECORD."""
    rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
    for row in rows:
        if row and row[0] in changed:
            body = changed[row[0]]
            row[1:3] = ["sha256=" + base64.urlsafe_b64encode(hashlib.sha256(body).digest()).rstrip(b"=").decode("ascii"),
                        str(len(body))]
    s = io.StringIO()
    csv.writer(s, delimiter=",", quotechar='"', lineterminator="\n").writerows(rows)
    return s.getvalue().encode("utf-8")


def build_sdist(sdist_directory, config_settings=None):
    name = _setuptools.build_sdist(sdist_directory, config_settings)
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is not None:
        reproducible(Path(sdist_directory) / name, int(epoch))
    return name


def reproducible(path: Path, epoch: int) -> None:
    """`path`'s members written again, in order, with `epoch` for every time and no owner, each mode and
    PKG-INFO's and setup.cfg's line ends as Linux gives them."""
    with tarfile.open(path, "r:gz") as src:
        fmt = src.format
        members = [(m, src.extractfile(m).read() if m.isfile() else None) for m in src.getmembers()]
    tar = io.BytesIO()
    with tarfile.open(fileobj=tar, mode="w", format=fmt) as out:
        for m, data in members:
            m.mtime, m.uid, m.gid, m.uname, m.gname = epoch, 0, 0, "", ""
            m.pax_headers = {k: v for k, v in m.pax_headers.items() if k not in _PAX_DROPPED}
            m.mode = _mode(m.mode, m.isdir())
            if data is not None:
                data = _text(m.name, data)
                m.size = len(data)
            out.addfile(m, io.BytesIO(data) if data is not None else None)
    with open(path, "wb") as f, gzip.GzipFile(filename="", mode="wb", fileobj=f, mtime=epoch) as gz:
        gz.write(tar.getvalue())
