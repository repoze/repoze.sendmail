##############################################################################
#
# Copyright (c) 2006 Zope Corporation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
import os
from setuptools import setup, find_packages

testing_extras = ['nose', 'coverage']
docs_extras = ['Sphinx', 'repoze.sphinx.autointerface']

requires = ['setuptools',
            'zope.interface>=3.6.0',
            'transaction']

here = os.path.abspath(os.path.dirname(__file__))
def _read_file(filename):
    try:
        with open(os.path.join(here, filename)) as f:
            return f.read()
    except IOError:  # Travis???
        return ''

README = _read_file('README.rst')
CHANGES = _read_file('CHANGES.rst')

setup(name='repoze.sendmail',
      version = '4.4.1',
      url='http://www.repoze.org',
      license='ZPL 2.1',
      description='Repoze Sendmail',
      author='Chris Rossi',
      author_email='repoze-dev@lists.repoze.org',
      long_description='\n\n'.join([README, CHANGES]),
      classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
        ],
      packages=find_packages(),
      namespace_packages=['repoze',],
      tests_require = requires,
      install_requires=requires,
      test_suite="repoze.sendmail",
      include_package_data = True,
      zip_safe = False,
      entry_points = """
          [console_scripts]
          qp = repoze.sendmail.queue:run_console
          """,
      extras_require = {
        'testing': requires + testing_extras,
        'docs': requires + docs_extras,
      },
)
