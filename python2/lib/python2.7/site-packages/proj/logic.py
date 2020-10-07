# -*- coding: utf-8 -*-
#
#  logic.py
#  proj
#

"""
High level operations for proj.
"""

import os
from typing import List, Tuple
import shutil
import glob
import datetime as dt
from functools import reduce

import click

from proj.configfile import Config
from proj import fs
from proj.exceptions import CommandError


def archive(src_path: str, config: Config, dry_run: bool = False) -> None:
    "Take a folder from the current directory and move it to the archive."
    if not os.path.exists(src_path):
        raise CommandError(f"no such file or folder: {src_path}")

    dest_path = _archive_path(src_path, config)

    print(src_path, "-->", dest_path)
    if not dry_run:
        _archive_project(src_path, dest_path, config)


def restore(dest_path: str, config: Config) -> None:
    "Take a project folder out of the archive and place it in the current working directory."
    if os.path.exists(dest_path):
        raise CommandError(f"file or directory already exists at: {dest_path}")

    source = _find_restore_match(dest_path, config.archive_dir)

    if fs.is_compressed(source):
        nice_source = fs.trim_archive_extension(source)
        print(nice_source, "-->", dest_path)

        shutil.unpack_archive(source, ".")
        os.unlink(source)
    else:
        print(source, "-->", dest_path)
        shutil.move(source, ".")


def list_projects(patterns: List[str], config: Config) -> List[str]:
    # strategy: pick the intersection of all the patterns the user provides
    globs = ["*{0}*".format(p) for p in patterns] + ["*"]

    match_sets = []
    offset = len(config.archive_dir) + 1
    for suffix in globs:
        glob_pattern = f"{config.archive_dir}/*/*/{suffix}"

        match_set = set()
        for full_filename in glob.glob(glob_pattern):
            tail_filename = full_filename[offset:]
            base = fs.trim_archive_extension(tail_filename)
            match_set.add(base)

        match_sets.append(match_set)

    final_set = reduce(lambda x, y: x.intersection(y), match_sets)

    return sorted(final_set)


def _archive_path(src_path: str, config: Config) -> str:
    "Find where to archive the path to based on when it was last changed."
    t = fs.last_modified(src_path)
    year, quarter = _to_quarter(t)
    return os.path.join(config.archive_dir, year, quarter, os.path.basename(src_path))


def _archive_project(src_path: str, dest_path: str, config: Config) -> None:
    parent_dir = os.path.dirname(dest_path)
    fs.mkdir(parent_dir)

    if config.compression:
        compression_format: str = config.compression_format  # type: ignore
        _archive_compressed(
            src_path, dest_path, compression_format, config.compression_ext
        )
    else:
        shutil.move(src_path, dest_path)


def _archive_compressed(
    src_path: str, dest_path: str, compression_format: str, compression_ext: str
) -> None:
    "Compress the folder into an file in the archive, then remove the original"
    dest_filename = dest_path + compression_ext

    try:
        shutil.make_archive(dest_path, compression_format, ".", src_path)

    except Exception as e:
        # remove the partially compressed file
        if os.path.exists(dest_filename):
            os.unlink(dest_filename)

        raise e

    shutil.rmtree(src_path)


def _find_restore_match(proj_name: str, archive_dir: str) -> str:
    base_pattern = os.path.join(archive_dir, "*", "*", proj_name)

    patterns = [base_pattern]
    for ext in fs.SUPPORTED_FORMATS.values():
        patterns.append(base_pattern + ext)

    matches = []
    for pattern in patterns:
        matches.extend(glob.glob(pattern))

    if not matches:
        raise CommandError(f"no project matches: {proj_name}")

    if len(matches) > 1:
        click.echo("Warning: multiple matches, picking the most recent", err=True)

    source = sorted(matches)[-1]

    return source


def _to_quarter(t: dt.datetime) -> Tuple[str, str]:
    return str(t.year), "q" + str(1 + (t.month - 1) // 3)
