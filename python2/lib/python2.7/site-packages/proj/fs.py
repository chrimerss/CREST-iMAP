# -*- coding: utf-8 -*-
#
#  fs.py
#  proj
#

"""
Filesystem operations.
"""

import os
from typing import Iterator

import arrow

from proj.exceptions import CommandError


SUPPORTED_FORMATS = {
    "bztar": ".tar.bz2",
    "gztar": ".tar.gz",
    "zip": ".zip",
    "tar": ".tar",
}


def mkdir(p: str) -> None:
    "The equivalent of 'mkdir -p' in shell."
    isdir = os.path.isdir

    stack = [os.path.abspath(p)]
    while not isdir(stack[-1]):
        parent_dir = os.path.dirname(stack[-1])
        stack.append(parent_dir)

    while stack:
        p = stack.pop()
        if not isdir(p):
            os.mkdir(p)


def is_compressed(path: str) -> bool:
    return any(path.endswith(ext) for ext in SUPPORTED_FORMATS.values())


def trim_archive_extension(path: str) -> str:
    "Remove any extension from the path due to compression."
    for ext in SUPPORTED_FORMATS.values():
        if path.endswith(ext):
            return path[: -len(ext)]

    return path


def last_modified(file_or_folder: str) -> arrow.Arrow:
    "Work out when the most recent file in a folder was modified."
    try:
        return max(
            mtime(f) for f in iter_files(file_or_folder) if not os.path.islink(f)
        )

    except ValueError:
        raise CommandError(f"no files in folder: {file_or_folder}")


def iter_files(file_or_folder: str) -> Iterator[str]:
    "Walk the given path and iterate over all files within it."
    if os.path.isdir(file_or_folder):
        for dirname, subdirs, filenames in os.walk(file_or_folder):
            for basename in filenames:
                filename = os.path.join(dirname, basename)
                yield filename
    else:
        # it's actually just a file
        yield file_or_folder


def mtime(filename: str) -> arrow.Arrow:
    return arrow.get(os.stat(filename).st_mtime)


def touch(filename: str) -> None:
    with open(filename, "a"):
        pass
