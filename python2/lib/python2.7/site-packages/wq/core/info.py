from __future__ import print_function
from wq.core import wq
import click


@wq.command()
@click.option("--output", help="Output filename")
@click.argument(
    "libraries",
    nargs=-1,
)
def versions(output, libraries):
    """
    List installed modules and dependencies.  Note: this is now
    just a wrapper around pip freeze.
    """
    click.echo(
        "Warning: wq versions is now an alias for pip freeze",
        err=True,
    )
    print_versions(output, libraries)


def print_versions(output, libraries=[]):
    try:
        from pip._internal.operations import freeze
    except ImportError:
        from pip.operations import freeze

    if libraries:
        click.echo(
            "Warning: The libraries argument has no effect",
            err=True,
        )

    deps = freeze.freeze()

    if output:
        with open(output, 'w') as f:
            for dep in deps:
                print(dep, file=f)
    else:
        for dep in deps:
            click.echo(dep)


DOC_LAYOUT = """---
order: {order}
---

wq {name}
{title_line}

wq {name}: {short_help}
Provided by [wq.{mod}](https://wq.io/wq.{mod}).

```shell
$ wq {name} --help

{help}
```"""

INDEX_LAYOUT = """---
order: 0
---

wq
==

The wq command line interface provides a number of utilities for creating and
deploying applications with the wq framework.

```shell
$ wq --help

{help}
```

## Commands

Command | Module | Description
--------|--------|-------------"""
INDEX_ROW = (
    "[{name}](https://wq.io/docs/wq-{name})"
    " | [wq.{mod}](https://wq.io/wq.{mod})"
    " | {short_help}"
)


@wq.command()
@click.pass_context
def _make_docs(ctx):
    command_list = []
    for i, (name, cmd) in enumerate(sorted(wq.commands.items())):
        if name.startswith('_'):
            continue

        with open('wq-%s.md' % name, 'w') as f:
            module_path = cmd.callback.__module__.split('.')
            if module_path[0] != 'wq':
                continue

            cctx = click.Context(cmd, info_name=name, parent=ctx.parent)
            command_info = dict(
                name=name,
                order=i+1,
                title_line='=' * (len(name) + 3),
                short_help=cmd.short_help,
                mod=module_path[1],
                help=cmd.get_help(cctx),
            )
            print(DOC_LAYOUT.format(**command_info), file=f)
            command_list.append(command_info)

    wq_help = wq.get_help(ctx.parent).split('Commands:')[0].strip()
    with open('wq.md', 'w') as f:
        print(INDEX_LAYOUT.format(
           short_help=wq.short_help,
           help=wq_help
        ), file=f)
        for command_info in command_list:
            print(INDEX_ROW.format(**command_info), file=f)
