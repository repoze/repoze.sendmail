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
import sys

from setuptools import setup, find_packages

testing_extras = ['nose', 'coverage']

requires = ['setuptools',
            'zope.interface>=3.6.0',
            'transaction']

if sys.version_info[:2] < (2, 6):
    # BBB Python 2.5 compat
    requires = ['setuptools',
                'zope.interface>=3.6.0',
                'transaction<1.2',
               ]

setup(name='repoze.sendmail',
      version = '3.2',
      url='http://www.repoze.org',
      license='ZPL 2.1',
      description='Repoze Sendmail',
      author='Chris Rossi',
      author_email='repoze-dev@lists.repoze.org',
      long_description='\n\n'.join([
          open('README.txt').read(),
          open('CHANGES.txt').read(),
          ]),
      classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2.5",
        "Programming Language :: Python :: 2.6",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.2",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: Jython",
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
      },
)
