from .parser import parse_xls, generate_names
from .renderer import render
from pkg_resources import resource_filename

TEMPLATE_NAMES = ('admin', 'models', 'rest', 'serializers')
DEFAULT_TEMPLATE = 'models'

DJANGO_TYPES = {
    # Map XForm field types to Django field types
    'barcode': False,
    'binary': 'FileField',
    'date': 'DateField',
    'dateTime': 'DateTimeField',
    'decimal': 'FloatField',
    'geopoint': 'PointField',
    'geoshape': 'PolygonField',
    'geotrace': 'LineStringField',
    'int': 'IntegerField',
    'select': 'CharField',
    'select1': 'CharField',
    'string': 'TextField',
    'time': 'TimeField',

    # Binary subtypes
    'image': 'ImageField',
}
IMAGE_SUBTYPES = ('image', 'photo', 'picture')


def django_context(xform_json):
    context = {
        'form': xform_json,
        'fields': xform_json['children'],
    }

    # Additional variations on name/title for use in models.py
    class_name, plural_name = generate_names(context['form']['name'])
    context['form'].update(
        class_name=class_name,
        field_name=class_name.lower(),
        verbose_name=context['form']['title'].lower(),
        verbose_name_plural=plural_name,
        urlpath=plural_name,
    )

    instance_name = context['form'].get('instance_name', '').strip()
    if instance_name.startswith('concat(') and instance_name.endswith(')'):
        label_template = ""
        for part in instance_name[7:-1].split(','):
            part = part.strip()
            if part.startswith('${') and part.endswith('}'):
                part = part.replace('${', '{{').replace('}', '}}')
            elif part[0] in ('"', "'") and part[-1] in ('"', "'"):
                part = part[1:-1]
            label_template += part
        context['form']['label_template'] = label_template

    def process_fields(fields):
        # Django field types
        for field in fields:
            if field.get('wq:nested', False):
                process_fields(field['children'])
                class_name, plural_name = generate_names(
                    field['name'], from_plural=True
                )
                field.update(
                    class_name=class_name,
                    verbose_name=class_name.lower(),
                    verbose_name_plural=plural_name,
                )
                context['form']['has_nested'] = True
                continue
            if 'type_info' not in field or 'note' in field['type']:
                continue

            if 'choices' in field:
                field['has_choices'] = True
                max_len = 0
                for choice in field['choices']:
                    if len(choice['name']) > max_len:
                        max_len = len(choice['name'])
                field['max_len'] = max_len

            if field['type'] in ('select1', 'select one'):
                qtype = 'select1'
            elif field['type'].startswith('select'):
                qtype = 'select'
            else:
                qtype = field['type_info']['bind']['type']

            field['type_is_%s' % qtype] = True
            field['subtype_is_%s' % field['type']] = True
            field['field_name'] = field['name'].lower().replace('-', '_')

            if 'wq:ForeignKey' in field:
                field['django_type'] = "ForeignKey"
            elif 'wq:length' in field and qtype == "string":
                field['django_type'] = "CharField"
            elif qtype == 'binary':
                field['django_type'] = DJANGO_TYPES['binary']
                for qt in IMAGE_SUBTYPES:
                    if qt in field['type']:
                        field['django_type'] = DJANGO_TYPES['image']
            else:
                field['django_type'] = DJANGO_TYPES[qtype]

            if qtype.startswith('geo'):
                context['form']['has_geo'] = True
                field['type_is_geo'] = True
    process_fields(context['fields'])
    return context


def xls2django(file_or_name, template_path=DEFAULT_TEMPLATE):
    xform_json = parse_xls(file_or_name)
    context = django_context(xform_json)
    if template_path in TEMPLATE_NAMES:
        template_path = resource_filename(
            'xlsconv', 'templates/%s.py-tpl' % template_path
        )
    return render(context, template_path)


def main():
    import sys
    print(xls2django(*sys.argv[1:]))


if __name__ == '__main__':
    main()
