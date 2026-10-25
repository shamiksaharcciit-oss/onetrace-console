"""The console's build backend: setuptools' own, with the sdist written again so that two builds of
one commit are the same bytes.

setuptools gives each member of the sdist its file's time, and the gzip header the time of the
build, so two builds from two checkouts of one commit differed in those times alone. Where
SOURCE_DATE_EPOCH is set, as a release build sets it to the commit's time, `build_sdist` writes the
same members again, in the same order with the same bytes and modes: every member's time that
epoch, no owner, and the gzip header's time that epoch too. Without it the sdist is setuptools'
as it was. The wheel is setuptools' own; it already takes its times from SOURCE_DATE_EPOCH.

pyproject.toml names this module (`backend-path`), and MANIFEST.in carries it into the sdist, so
a wheel builds from the sdist by the same backend.
"""
from __future__ import annotations

import gzip
import io
import os
import tarfile
from pathlib import Path

from setuptools import build_meta as _setuptools
from setuptools.build_meta import *  # noqa: F401,F403  (every hook setuptools gives, unchanged)

#: The PAX fields that carry a time or an owner; the epoch and the plain fields stand for them.
_PAX_DROPPED = ("mtime", "atime", "ctime", "uid", "gid", "uname", "gname")


def build_sdist(sdist_directory, config_settings=None):
    name = _setuptools.build_sdist(sdist_directory, config_settings)
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is not None:
        reproducible(Path(sdist_directory) / name, int(epoch))
    return name


def reproducible(path: Path, epoch: int) -> None:
    """`path`'s members written again, in order, with `epoch` for every time and no owner."""
    with tarfile.open(path, "r:gz") as src:
        fmt = src.format
        members = [(m, src.extractfile(m).read() if m.isfile() else None) for m in src.getmembers()]
    tar = io.BytesIO()
    with tarfile.open(fileobj=tar, mode="w", format=fmt) as out:
        for m, data in members:
            m.mtime, m.uid, m.gid, m.uname, m.gname = epoch, 0, 0, "", ""
            m.pax_headers = {k: v for k, v in m.pax_headers.items() if k not in _PAX_DROPPED}
            out.addfile(m, io.BytesIO(data) if data is not None else None)
    with open(path, "wb") as f, gzip.GzipFile(filename="", mode="wb", fileobj=f, mtime=epoch) as gz:
        gz.write(tar.getvalue())
