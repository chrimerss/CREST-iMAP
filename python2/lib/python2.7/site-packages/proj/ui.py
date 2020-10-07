# -*- coding: utf-8 -*-
#
#  ui.py
#  proj
#

import sys
from typing import NoReturn

import click


def bail(message: str) -> NoReturn:
    click.echo(message, err=True)
    sys.exit(1)
