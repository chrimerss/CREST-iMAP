try:
    from py_mini_racer import py_mini_racer
except ImportError:
    has_mini_racer = False
else:
    has_mini_racer = True
from contextlib import contextmanager
import os
import base64

js_dir = os.path.dirname(__file__)
with open(os.path.join(js_dir, 'env.js')) as f:
    env = f.read()


def execjs(filename, method, argument=None, callback=False,
           argv=[], base_dir=None, write_dir=None):
    with open(os.path.join(js_dir, filename)) as f:
        lib = f.read()

    argv = [filename] + argv
    with get_js_env(base_dir, write_dir, argv) as ctx:
        ctx.eval(lib)
        if callback:
            ctx.call("wrapCallback", method)
            result = ctx.call("lastCallback", argument)
        else:
            result = ctx.call("module.exports." + method, argument)
        log = ctx.eval('console.history')

    return result, log


@contextmanager
def get_js_env(base_dir=None, write_dir=None, argv=[]):
    ctx = py_mini_racer.MiniRacer()
    ctx.eval(env)
    ctx.call('setArgV', ['node'] + argv)

    base_dir = os.path.abspath(base_dir)
    if write_dir and not os.path.abspath(write_dir).startswith(base_dir):
        read_files(ctx, write_dir)
    read_files(ctx, base_dir)
    yield ctx
    delete_files(ctx, write_dir)
    write_files(ctx, write_dir)


def read_files(ctx, base_dir):
    if base_dir is None:
        return
    base_dir = os.path.abspath(base_dir)
    ctx.call('setBasePath', base_dir)
    seen = set()
    for base, dirs, files in os.walk(base_dir, followlinks=True):
        if base in seen:
            continue
        seen.add(base)
        for filename in files:
            path = os.path.join(base, filename)
            with open(path, 'rb') as f:
                contents = f.read()
                try:
                    contents = contents.decode('utf-8')
                except UnicodeDecodeError:
                    contents = base64.b64encode(contents)
                    contents = 'base64,' + contents.decode('ascii')
                ctx.call('addFile', path, contents)


def delete_files(ctx, write_dir):
    dirs = ctx.eval('_deleteDirs')
    files = ctx.eval('_deleteFiles')

    if (dirs or files) and not write_dir:
        raise Exception("Attempt to delete but no write_dir is set")

    write_dir = os.path.abspath(write_dir)

    for name, val in files.items():
        path = os.path.abspath(name)
        if not path.startswith(write_dir):
            raise Exception("Attempt to delete file outside of write_dir")
        if os.path.exists(path):
            os.unlink(path)

    for name in sorted(dirs, reverse=True):
        path = os.path.abspath(name)
        if not path.startswith(write_dir):
            raise Exception("Attempt to delete directory outside of write_dir")
        if os.path.exists(path):
            os.rmdir(path)


def write_files(ctx, write_dir):
    dirs = ctx.eval('_writeDirs')
    files = ctx.eval('_writeFiles')

    if (dirs or files) and not write_dir:
        raise Exception("Attempt to write but no write_dir is set")

    write_dir = os.path.abspath(write_dir)

    file_dirs = set(
        os.path.dirname(name)
        for name in files
    )
    for name in sorted(dirs):
        path = os.path.abspath(name)
        if not path.startswith(write_dir):
            continue
        if path in file_dirs:
            os.makedirs(path, exist_ok=True)

    for name, contents in files.items():
        path = os.path.abspath(name)
        if not path.startswith(write_dir):
            raise Exception("Attempt to write to file outside of write_dir")
        with open(path, 'wb') as f:
            if contents.startswith('base64,'):
                contents = base64.b64decode(contents[7:])
            else:
                contents = contents.encode('utf-8')
            f.write(contents)
