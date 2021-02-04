import click
from .decorators import config_group
import yaml
from pkg_resources import iter_entry_points


# Core wq CLI
@config_group()
@click.option(
    '-c', '--config',
    default='wq.yml',
    type=click.Path(),
    help='Path to configuration file (default is wq.yml).'
)
@click.pass_context
def wq(ctx, config):
    """
    wq is a suite of command line utilities for building citizen science apps.
    Each of the commands below can be configured by creating a wq.yml file in
    the current directory.  Many of the commands can also be configured via
    command line options.
    """
    if ctx.obj:
        # Allow for multiple invocations without resetting context
        return

    try:
        conf = Config(yaml.load(open(config)))
        conf.filename = config
    except IOError:
        if config != "wq.yml":
            raise
        conf = Config()
    ctx.obj = conf
    ctx.default_map = conf


class Config(dict):
    filename = None


wq.pass_config = click.make_pass_decorator(Config)


# Load custom commands from other modules
module_names = []
for module in iter_entry_points(group='wq', name=None):
    module_names.append(module.name)
    module.load()

expected = [
    'wq.app',
    'wq.core',
    'wq.db',
    'wq.io',
    'wq.start',
]
missing = set(expected) - set(module_names)

# Update help text with list of installed modules
if module_names:
    wq.help += "\n\nInstalled modules: " + ", ".join(sorted(module_names))
if missing:
    wq.help += "\n\nMissing modules: " + ", ".join(sorted(missing))
    wq.help += "\n(try installing the 'wq' metapackage)"
