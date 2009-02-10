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
"""Mail delivery names vocabulary test

$Id: test_vocabulary.py 69432 2006-08-12 17:36:18Z philikon $
"""
import unittest
from zope.testing.doctestunit import DocTestSuite
from zope.component.testing import setUp, tearDown

def test_suite():
    return unittest.TestSuite([
        DocTestSuite('repoze.sendmail.vocabulary',
                     setUp=setUp, tearDown=tearDown),
        ])

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
