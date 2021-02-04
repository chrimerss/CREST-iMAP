from wq.core import wq
import click
import os
from xlsconv import parse_xls, xls2django, xls2html, html_context, render
from pkg_resources import resource_filename
import subprocess
import json
from difflib import unified_diff
from pyxform.question_type_dictionary import QUESTION_TYPE_DICT as QTYPES


templates = resource_filename('wq.start', 'master_templates')
# resource_filename not returning absolute path after pip install
if os.sep not in templates:
    import wq as wq_module
    templates = wq_module.__path__[0] + os.sep + templates


@wq.command()
@click.argument(
    "xlsform",
    required=True,
    type=click.Path(exists=True),
)
@click.option(
    "--input-dir",
    default="../master_templates",
    type=click.Path(exists=True),
    help="Source / master templates",
)
@click.option(
    "--django-dir",
    default=".",
    type=click.Path(exists=True),
    help="Root of Django project",
)
@click.option(
    "--template-dir",
    default="../templates",
    type=click.Path(exists=True),
    help="Path to shared template directory",
)
@click.option(
    "--form-name",
    help="Name to use for Django app and template prefix",
)
@click.option(
    "--with-admin/--no-admin",
    default=False,
    help="Generate admin.py",
)
@click.option(
    "--force", "-f",
    is_flag=True,
    default=False,
    help="Answer yes to all prompts",
)
def addform(xlsform, input_dir, django_dir, template_dir,
            form_name, with_admin, force):
    """
    Convert an XLSForm into a Django app for wq.  Generates Python and mustache
    files including:

    \b
        db/[form_name]/models.py
        db/[form_name]/rest.py
        templates/[form_name]_detail.html
        templates/[form_name]_edit.html
        templates/[form_name]_list.html
    """

    xls_json = parse_xls(xlsform)
    if not form_name:
        form_name = xls_json['name']

    if not os.path.exists(os.path.join(django_dir, form_name)):
        os.mkdir(os.path.join(django_dir, form_name))

    if not os.path.exists(os.path.join(django_dir, form_name, 'migrations')):
        os.mkdir(os.path.join(django_dir, form_name, 'migrations'))

    create_file(
        [django_dir, form_name, '__init__.py'],
        "",
        overwrite=force,
    )

    create_file(
        [django_dir, form_name, 'migrations', '__init__.py'],
        "",
        overwrite=force,
    )

    create_file(
        [django_dir, form_name, 'models.py'],
        xls2django(xlsform, 'models'),
        overwrite=force,
    )

    has_nested = False
    for field in xls_json['children']:
        if field.get('wq:nested', False):
            has_nested = True
    if has_nested:
        create_file(
            [django_dir, form_name, 'serializers.py'],
            xls2django(xlsform, 'serializers'),
            overwrite=force,
        )

    create_file(
        [django_dir, form_name, 'rest.py'],
        xls2django(xlsform, 'rest'),
        overwrite=force,
    )
    if with_admin:
        create_file(
            [django_dir, form_name, 'admin.py'],
            xls2django(xlsform, 'admin'),
            overwrite=force,
        )

    template_types = set(['detail', 'edit', 'list'])
    for field in xls_json['children']:
        if 'geo' in field['type']:
            if 'popup' in template_types:
                print("Warning: multiple geometry fields found.")
            template_types.add('popup')
    for tmpl in template_types:
        create_file(
            [template_dir, "%s_%s.html" % (form_name, tmpl)],
            xls2html(xlsform, os.path.join(input_dir, "%s.html" % tmpl)),
            overwrite=force,
        )

    settings_path = None
    for path, dirs, files in os.walk(django_dir):
        for filename in files:
            if filename == 'settings.py':
                settings_path = (path, filename)
            elif path.endswith('/settings') and filename == 'base.py':
                settings_path = (path[:-9], 'settings', filename)

    if not settings_path:
        return

    new_settings = []
    app_section = False
    has_app = False
    for row in open(os.path.join(*settings_path)):
        if 'INSTALLED_APPS' in row:
            app_section = True
        elif app_section:
            if ')' in row or ']' in row:
                app_section = False
                if not has_app:
                    new_settings.append(
                        "    '%s',%s" % (form_name, os.linesep)
                    )
            else:
                if '"%s"' % form_name in row or "'%s'" % form_name in row:
                    has_app = True
        new_settings.append(row)
    create_file(
        settings_path, "".join(new_settings), overwrite=force, show_diff=True
    )
    result = subprocess.check_output(
        [os.path.join(django_dir, 'manage.py'), 'makemigrations']
    ).decode('utf-8').strip()
    print(result)
    if 'No changes' in result:
        return
    migrate = force or click.confirm("Update database schema?", default=True)
    if not migrate:
        return
    subprocess.call(
        [os.path.join(django_dir, 'manage.py'), 'migrate']
    )


@wq.command()
@click.option(
    "--input-dir",
    default="../master_templates",
    type=click.Path(exists=True),
    help="Source / master templates",
)
@click.option(
    "--django-dir",
    default=".",
    type=click.Path(exists=True),
    help="Root of Django project",
)
@click.option(
    "--template-dir",
    default="../templates",
    type=click.Path(exists=True),
    help="Path to shared template directory",
)
@click.option(
    '-f',
    '-overwrite',
    default=False,
    is_flag=True,
    help="Replace existing templates",
)
def maketemplates(input_dir, django_dir, template_dir, overwrite):
    """
    Generate mustache templates for wq.db.rest.  Automatically discovers all
    registered models through ./manage.py dump_config.

    \b
        templates/[model_name]_detail.html
        templates/[model_name]_edit.html
        templates/[model_name]_list.html
    """
    result = subprocess.check_output(
        [os.path.join(django_dir, 'manage.py'), 'dump_config']
    )
    config = json.loads(result.decode('utf-8'))

    has_diff = False

    for page in config['pages'].values():
        if not page.get('list', None):
            continue

        if has_diff == 'skipall':
            break

        def process_fields(fields):
            for field in fields:
                if field['type'] in ('repeat', 'group'):
                    field['wq:nested'] = True
                    if field['type'] == 'repeat':
                        field['wq:many'] = True
                    process_fields(field['children'])
                elif field['type'] in QTYPES:
                    field['type_info'] = QTYPES[field['type']]
                else:
                    field['type_info'] = {'bind': {'type': field['type']}}

        process_fields(page['form'])
        context = html_context({
            'name': page['name'],
            'title': page['name'],
            'children': page['form'],
        })
        context['form']['urlpath'] = page['url']

        template_types = set(page.get('modes', ['detail', 'edit', 'list']))

        has_geo = False
        for field in page['form']:
            if 'geo' in field['type']:
                if has_geo:
                    print("Warning: multiple geometry fields found.")
                has_geo = True

        if page.get('map', None):
            has_geo = True

        if has_geo:
            context['form']['has_geo'] = True
            template_types.add('popup')

        for tmpl in template_types:
            has_diff = create_file(
                [template_dir, "%s_%s.html" % (page['name'], tmpl)],
                render(context, os.path.join(input_dir, '%s.html' % tmpl)),
                overwrite=overwrite,
                previous_diff=has_diff,
            )
            if has_diff == 'skipall':
                break


def create_file(path, contents, overwrite=False,
                show_diff=False, previous_diff=False):
    filename = os.path.join(*path)
    has_diff = previous_diff
    if os.path.exists(filename) and not overwrite:
        existing_file = open(filename, 'r')
        existing_content = existing_file.read()
        if existing_content.strip() == contents.strip():
            return False

        def print_diff():
            diff = unified_diff(
                existing_content.split('\n'),
                contents.split('\n'),
                fromfile="%s (current)" % path[-1],
                tofile="%s (new)" % path[-1],
            )
            for row in diff:
                print(row)

        if show_diff:
            print_diff()
            message = "Update %s? [Y/n/d/?]"
            default_choice = 'y'
        else:
            if not previous_diff:
                choice = click.prompt('Update templates? [y/n]')
                if choice.lower() != 'y':
                    print("Skipping template updates.")
                    return 'skipall'

            message = "%s already exists; overwrite? [y/n/d/?]"
            default_choice = None

        has_diff = True
        choice = ''
        while choice.lower() not in ('y', 'n'):
            if path[-2] == 'settings':
                filename = os.path.join(*path[-2:])
            else:
                filename = path[-1]
            choice = click.prompt(
                message % filename, default=default_choice, show_default=False
            )
            if choice == '' and show_diff:
                choice = 'y'
            if choice.lower() == 'n':
                return has_diff
            elif choice.lower() == '?':
                print(
                    '  y - overwrite\n'
                    '  n - skip\n'
                    '  d - show diff\n'
                    '  ? - show help'
                )
            elif choice.lower() == 'd':
                print_diff()
    out = open(os.path.join(*path), 'w')
    out.write(contents)
    out.close()
    return has_diff
