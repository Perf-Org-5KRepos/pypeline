# #############################################################################
# conf.py
# =======
# Author : Sepand KASHANI [sep@zurich.ibm.com]
# Revision : 0.0
# Last updated : 2018-05-01 07:56:45 UTC
# #############################################################################

from typing import Mapping

import configparser
import datetime
import pathlib
import re


def setup_config() -> configparser.ConfigParser:
    """
    Load information contained in `setup.cfg`.
    """
    sphinx_src_dir = pathlib.Path(__file__).parent
    setup_path = sphinx_src_dir / '..' / '..' / 'setup.cfg'
    setup_path = setup_path.resolve(strict=True)

    with setup_path.open(mode='r') as f:
        cfg = configparser.ConfigParser()
        cfg.read_file(f)
    return cfg


def pkg_info() -> Mapping:
    """
    Load information contained in `PKG-INFO`.
    """
    sphinx_src_dir = pathlib.Path(__file__).parent
    info_path = sphinx_src_dir / '..' / '..' / 'pypeline.egg-info' / 'PKG-INFO'
    info_path = info_path.resolve(strict=True)

    # Pattern definitions
    pat_version = r'Version: (.+)$'

    with info_path.open(mode='r') as f:
        info = dict(version=None)
        for line in f:
            m = re.match(pat_version, line)
            if m is not None:
                info['version'] = m.group(1)
    return info


# -- Project information -----------------------------------------------------
cfg, info = setup_config(), pkg_info()
project = cfg.get('metadata', 'name')
copyright = (f'{datetime.date.today().year}, '
             'Imaging of Things Team (ImoT), IBM Research Zurich')
author = cfg.get('metadata', 'author')
version = release = info['version']


# -- General configuration ---------------------------------------------------
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.doctest',
    'sphinx.ext.intersphinx',
    'sphinx.ext.todo',
    'sphinx.ext.viewcode',
]

templates_path = ['_templates']
master_doc = 'index'
exclude_patterns = []
pygments_style = 'sphinx'


# -- Options for HTML output -------------------------------------------------
html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']


# -- Options for HTMLHelp output ---------------------------------------------
htmlhelp_basename = 'pypelinedoc'


# -- Extension configuration -------------------------------------------------
# -- Options for intersphinx extension ---------------------------------------
intersphinx_mapping = {'https://docs.python.org/': None}
