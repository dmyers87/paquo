import os
import sys
from pathlib import Path
from typing import Tuple, List

import jpype


def find_qupath() -> Tuple[Path, Path, Path, List[str]]:
    """find current qupath installation and jvm paths/options

    For now this supports a qupath which ships its own JRE installation
    and was installed via `conda install -c sdvillal qupath`

    Returns
    -------
    qupath_jvm_info:
        a tuple (app_dir, runtime_dir, jvm_path, jvm_options)
    """
    # test if we're running in conda
    prefix = os.environ.get('CONDA_PREFIX')
    if not prefix:
        # for now we require the conda install
        raise NotImplementedError("paquo requires a conda installed qupath")
    conda_prefix = Path(prefix)

    # hardcoded paths as in the conda recipe at:
    # github.com/bayer-science-for-a-better-life/qupath-feedstock
    if sys.platform == "linux" or sys.platform == "linux2":
        app_dir = conda_prefix / 'opt' / 'QuPath' / 'lib' / 'app'
        runtime_dir = conda_prefix / 'opt' / 'QuPath' / 'lib' / 'runtime'
        jvm_path = runtime_dir / 'lib' / 'server' / 'libjvm.so'
        jvm_options = []

    elif sys.platform == "darwin":
        qupath_dir = conda_prefix / 'bin' / 'QuPath.app'
        app_dir = qupath_dir / 'Contents' / 'app'
        runtime_dir = qupath_dir / 'Contents' / 'runtime' / 'Contents' / 'Home'
        jvm_path = qupath_dir / 'Contents' / 'runtime' / 'Contents' / 'MacOS' / 'libjli.dylib'
        jvm_options = [
            f'-Djava.library.path={app_dir}:{qupath_dir}/Contents/MacOS',
            f'-Djava.launcher.path={qupath_dir}/Contents/MacOS',
        ]

    elif sys.platform == "win32":
        app_dir = conda_prefix / 'Library' / 'QuPath' / 'app'
        runtime_dir = conda_prefix / 'Library' / 'QuPath' / 'runtime'
        jvm_path = None  # TODO
        jvm_options = []

    else:
        raise ValueError(f'Unknown platform {sys.platform}')

    if not (app_dir.is_dir() and runtime_dir.is_dir() and jvm_path.is_file()):
        raise FileNotFoundError('qupath installation is incompatible')

    return app_dir, runtime_dir, jvm_path, jvm_options


def start_jvm(finder=None):
    if finder is None:
        finder = find_qupath

    if not jpype.isJVMStarted():
        # For the time being, we assume qupath is our JVM of choice
        app_dir, runtime_dir, jvm_path, jvm_options = finder()
        # This is not really needed, but beware we might need SL4J classes (see warning)
        jpype.addClassPath(str(app_dir / '*'))
        jpype.startJVM(str(jvm_path), *jvm_options, convertStrings=False)
