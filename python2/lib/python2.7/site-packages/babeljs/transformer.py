from .jscontext import get_context, ContextException
from babeljs.source import get_abspath, EXTERNAL_PLUGINS


class TransformError(Exception):
    pass


class Transformer(object):

    def __init__(self, runtime='auto', **_opts):
        self.runtime = runtime
        opts = {
            'ast': False,
            'presets': ['es2015', 'stage-0', 'react']
        }
        opts.update(_opts)
        plugins = opts.get('plugins', [])

        babel_path = get_abspath('babeljs/browser.js')

        codes = []
        with open(babel_path) as f:
            codes.append(f.read())
        codes.append("""
            var babel;
            if (typeof Babel != 'undefined')
                babel = Babel;
            else
                babel = module.exports;
        """)

        codes.append("""
            if (typeof console == 'undefined') {
                console = {};
                ['log', 'error', 'warn', 'info', 'debug'].forEach(
                    function(key) {
                        console[key] = function() {};
                    }
                );
            }
        """)

        for plugin in plugins:
            if plugin in EXTERNAL_PLUGINS:
                plugin_path = get_abspath(
                    'babeljs/babel-plugin-{}.min.js'.format(plugin)
                )
                with open(plugin_path) as f:
                    codes.append(f.read())
                codes.append("""
                    babel.registerPlugin(
                        "{}",
                        this["babel-plugin-{}"] || module.exports
                    );
                """.format(plugin, plugin))
        try:
            self.opts = opts
            self.context = get_context(self.runtime)
            self.context.eval(''.join(codes))
        except:
            raise TransformError()

    def transform_string(self, js_content, **_opts):
        opts = dict(self.opts, **_opts)
        try:
            result = self.context.call('babel.transform', js_content, opts)
            return result['code']
        except ContextException as e:
            raise TransformError(e.args[0])

    def transform(self, js_path, **opts):
        with open(js_path, 'r') as f:
            return self.transform_string(f.read(), **opts)


def transform(js_path, **opts):
    return Transformer(**opts).transform(js_path)


def transform_string(js_content, **opts):
    return Transformer(**opts).transform_string(js_content)
