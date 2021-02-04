from .execjs import execjs, has_mini_racer
import os
from distutils.dir_util import copy_tree


class RJSException(Exception):
    pass


def optimize(conf=None, working_directory=None, **kwargs):
    if conf is None:
        conf = kwargs
    if working_directory is None:
        working_directory = "."
    if 'dir' in conf:
        write_dir = os.path.join(working_directory, conf['dir'])
    else:
        write_dir = None

    if 'appDir' in conf:
        source_dir = os.path.join(working_directory, conf['appDir'])
    else:
        source_dir = None

    if not has_mini_racer:
        if source_dir and write_dir:
            print(
                "Warning: PyMiniRacer not found. "
                "Copying {source} to {dest} without compilation.".format(
                    source=os.path.normpath(source_dir),
                    dest=os.path.normpath(write_dir),
                )
            )
            copy_tree(source_dir, write_dir)
            with open(os.path.join(write_dir, 'build.txt'), 'w') as f:
                f.write("# Skipped r.js build (PyMiniRacer not found)\n")
            return
        else:
            raise RJSException("PyMiniRacer not found")

    result, log = execjs(
        filename="r.js",
        method="optimize",
        argument=conf,
        callback=True,
        argv=['-o', 'dummy.json'],
        base_dir=working_directory,
        write_dir=write_dir,
    )
    if log and "Error" in log[-1]:
        raise RJSException(log[-1])
    else:
        return result
