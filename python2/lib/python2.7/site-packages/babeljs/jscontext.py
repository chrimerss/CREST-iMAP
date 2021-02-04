try:
    from py_mini_racer import py_mini_racer
except ImportError:
    py_mini_racer = None

try:
    from shutil import which
except ImportError:
    from distutils.spawn import find_executable as which

import subprocess
import json
import tempfile
import os


if py_mini_racer:
    ContextException = py_mini_racer.MiniRacerBaseException
else:
    class ContextException(Exception):
        pass


class NodeException(ContextException):
    pass


def get_context(runtime='auto'):
    if runtime not in ('auto', 'miniracer', 'node'):
        raise ContextException('Unknown runtime: %s' % runtime)

    if runtime == 'auto':
        # Assume node if py_mini_racer is not installed
        if py_mini_racer is not None:
            runtime = 'miniracer'
        else:
            runtime = 'node'

    if runtime == 'miniracer':
        if py_mini_racer is None:
            raise ContextException("PyMiniRacer requested but not installed!")
        return py_mini_racer.MiniRacer()
    else:
        return MinimalNodeWrapper()


class MinimalNodeWrapper(object):
    """
    Bare-minimum node wrapper providing an API like MiniRacer.
    """

    RESULT_FLAG = '__result__'

    def __init__(self):
        self.code = ""
        self.executable = None

        for name in ('node', 'nodejs'):
            if which(name):
                self.executable = name
                break

        if not self.executable:
            raise NodeException("Node.js requested but not installed!")

    def eval(self, code):
        # Note: Proper eval would actually execute code and return last result,
        # but we don't need that in this case.
        self.code += code

    def call(self, function, *args):
        # Dump "eval" code to file, run node, and parse result. Makes some
        # assumptions about code structure, which are safe in this case.

        self.code += """
            console.log(
                "{flag}",
                JSON.stringify({function}({args}))
            );
        """.format(
            flag=self.RESULT_FLAG,
            function=function,
            args=", ".join(
                json.dumps(arg)
                for arg in args
            ),
        )

        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.js',
            delete=False
        ) as f:
            f.write(self.code)

        try:
            result = subprocess.check_output(
                [self.executable, f.name],
                stderr=subprocess.STDOUT,
            )
        except subprocess.CalledProcessError:
            result = None

        try:
            os.remove(f.name)
        except OSError:
            pass

        if not result:
            raise NodeException("Compilation Failed")

        result_lines = result.decode('utf-8').strip().split('\n')
        last_line = result_lines[-1]
        if not last_line.startswith(self.RESULT_FLAG):
            raise NodeException("Compilation Failed: %s" % last_line)

        last_line = last_line[len(self.RESULT_FLAG) + 1:]
        return json.loads(last_line)
