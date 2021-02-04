from django.template.backends.base import BaseEngine
try:
    from django.template.exceptions import TemplateDoesNotExist
except ImportError:
    from django.template.base import TemplateDoesNotExist
from django.template.context import _builtin_context_processors
from django.utils.module_loading import import_string
from django.utils.functional import cached_property

import pystache
from pystache.common import (
    TemplateNotFoundError as PystacheTemplateDoesNotExist
)

import os


class Mustache(BaseEngine):
    """
    Mustache template backend for Django 1.8+
    """

    app_dirname = "mustache"

    def __init__(self, params):
        params = params.copy()
        self.options = params.pop('OPTIONS').copy()
        self.options.setdefault('partial_dir', 'partials')
        self.options.setdefault('file_extension', 'html')

        super(Mustache, self).__init__(params)

        dirs = self.template_dirs
        if self.options['partial_dir']:
            for path in self.template_dirs:
                dirs += (os.path.join(path, self.options['partial_dir']),)

        self.engine = Engine(
            search_dirs=dirs,
            file_extension=self.options['file_extension'],
        )

    @cached_property
    def template_context_processors(self):
        paths = _builtin_context_processors + tuple(self.options.get(
            'context_processors', []
        ))
        processors = []
        for path in paths:
            processors.append(import_string(path))
        return processors

    def get_template(self, template_name):
        template_name = template_name.replace(
            '.' + self.engine.file_extension, ''
        )
        try:
            template = self.engine.load_template(template_name)
        except PystacheTemplateDoesNotExist as e:
            raise TemplateDoesNotExist(e)
        return Template(template, self)


class Template(object):
    """
    Analogue to django.template.backends.django.Template, with a bit of
    django.template.context.RequestContext built in.
    """
    def __init__(self, template, backend):
        self.template = template
        self.backend = backend

    def render(self, context=None, request=None):
        contexts = []

        if context and not request:
            request = context.get('request', None)

        if request:
            for fn in self.backend.template_context_processors:
                contexts.append(fn(request))

        if context:
            contexts.append(context)

        return self.backend.engine.render(
            self.template,
            *contexts
        )


class Engine(pystache.Renderer):
    """
    Rough analogue to django.template.engine.Engine, but almost entirely
    handled by Pystache.
    """
    def str_coerce(self, val):
        if val is None:
            return ""
        return str(val)
