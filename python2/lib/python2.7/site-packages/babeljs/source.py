__author__ = 'yetone'

from os.path import abspath, dirname, join, isfile


ROOT = abspath(join(dirname(__file__), 'static'))
EXTERNAL_PLUGINS = (
    'transform-vue-jsx',
)


def get_abspath(js_file):
    path = join(ROOT, js_file)
    if isfile(path):
        return path
    else:
        raise IOError('%s: Could not find specified file.' % path)
