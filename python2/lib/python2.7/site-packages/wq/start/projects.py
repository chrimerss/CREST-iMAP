from wq.core import wq
import click
import os
import shutil
from django.core.management import call_command
from django.core.management.commands import startproject
from pkg_resources import resource_filename
from wq.core.info import print_versions
from .version import VERSION


template = resource_filename('wq.start', 'django_project')
# resource_filename not returning absolute path after pip install
if os.sep not in template:
    import wq as wq_module
    template = wq_module.__path__[0] + os.sep + template


class StartProjectCommand(startproject.Command):
    def add_arguments(self, parser):
        super(StartProjectCommand, self).add_arguments(parser)
        parser.add_argument('--domain', help="Web Domain")
        parser.add_argument('--app-id', help="App Identifier")
        parser.add_argument('--with-gis', help="Enable GeoDjango")
        parser.add_argument('--wq-start-version', help="wq start version")


@wq.command()
@click.argument("project_name", required=True)
@click.argument("destination", required=False)
@click.option(
    "-d", "--domain", help='Web domain (e.g. example.wq.io)'
)
@click.option(
    "-i", "--app-id", help="Application ID (e.g. io.wq.example)"
)
@click.option(
    "--with-gis/--without-gis", default=True, help="Enable GeoDjango"
)
def start(project_name, destination, domain=None, app_id=None, with_gis=True):
    """
    Start a new project with wq.app and wq.db.  A new Django project will be
    created from a wq-specific template.  After running this command, you may
    want to do the following:

    \b
        sudo chown www-data media/
        cd app
        wq init

    See https://wq.io/docs/setup for more tips on getting started with wq.
    """

    if domain is None:
        domain = '{}.example.org'.format(project_name)

    if app_id is None:
        app_id = '.'.join(reversed(domain.split('.')))

    args = [project_name]
    if destination:
        args.append(destination)
    kwargs = dict(
        template=template,
        extensions="py,yml,conf,html,sh,js,css,json,xml".split(","),
        domain=domain,
        app_id=app_id,
        wq_start_version=VERSION,
        with_gis=with_gis,
    )
    call_command(StartProjectCommand(), *args, **kwargs)

    path = destination or project_name
    print_versions(os.path.join(path, 'requirements.txt'))
    shutil.copytree(
        resource_filename('xlsconv', 'templates'),
        os.path.join(path, 'master_templates'),
        ignore=shutil.ignore_patterns("*.py-tpl"),
    )
