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

from setuptools import setup, find_packages

setup(name='repoze.sendmail',
      version = '2.4dev',
      url='http://www.repoze.org',
      license='ZPL 2.1',
      description='Repoze Sendmail',
      author='Chris Rossi',
      author_email='repoze-dev@lists.repoze.org',
      long_description='\n\n'.join([
          open('README.txt').read(),
          open('CHANGES.txt').read(),
          ]),
      packages=find_packages(),
      namespace_packages=['repoze',],
      tests_require = [],
      install_requires=['setuptools',
                        'zope.interface>=3.6.0',
                        'transaction',
                       ],
      test_suite="repoze.sendmail",
      include_package_data = True,
      zip_safe = False,
      entry_points = """
          [console_scripts]
          qp = repoze.sendmail.queue:run_console
          """,
      )
