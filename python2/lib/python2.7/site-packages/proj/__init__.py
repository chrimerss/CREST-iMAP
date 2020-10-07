# -*- coding: utf-8 -*-
#
#  __init__.py
#  proj
#

from __future__ import print_function

__author__ = "Lars Yencken"
__email__ = "lars@yencken.org"
__version__ = "0.2.0"

import os
from typing import List

import click

from proj.configfile import Config, NoConfigError
from proj import logic
from proj.ui import bail


@click.group()
def main():
    """
    proj is a tool for managing many different projects, and archiving
    projects that you're no longer actively working on.

    It assumes you have a working folder containing active projects,
    and an archive folder with inactive projects. proj helps organise
    inactive projects by year and by quarter (e.g. 2013/q3/my-project).

    proj needs an archive directory specified by the PROJ_ARCHIVE
    environment variable.
    """
    pass


@click.command()
@click.argument("folder", nargs=-1)
@click.option("-n", "--dry-run", is_flag=True, help="Don't make any changes")
def archive(folder: List[str], dry_run: bool = False):
    "Move an active project to the archive."
    config = _get_config()

    for f in folder:
        if not os.path.exists(f):
            bail("folder does not exist: " + f)

        logic.archive(f, config, dry_run=dry_run)


@click.command()
@click.argument("pattern", nargs=-1)
def list(pattern: List[str]) -> None:
    "List the contents of the archive directory."
    config = _get_config()

    projects = logic.list_projects(pattern, config)

    for m in projects:
        print(m)


@click.command()
@click.argument("folder")
def restore(folder: str) -> None:
    "Restore a project from the archive into the current directory."
    config = _get_config()

    if os.path.exists(folder):
        bail("a folder of the same name already exists!")

    logic.restore(folder, config)


def _get_config() -> Config:
    try:
        config = Config.autoload()

    except NoConfigError:
        bail(
            "No config file found at ~/.proj.yml -- please set one up\n"
            "See https://github.com/larsyencken/proj/ for an example"
        )

    return config


main.add_command(archive)
main.add_command(list)
main.add_command(restore)


if __name__ == "__main__":
    main()
