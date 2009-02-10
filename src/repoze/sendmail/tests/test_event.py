##############################################################################
#
# Copyright (c) 2003 Zope Corporation and Contributors.
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
"""Mailer Events Tests

$Id: test_event.py 66922 2006-04-12 23:28:07Z jinty $
"""
from unittest import TestCase, TestSuite, makeSuite

from zope.interface.verify import verifyObject

from repoze.sendmail.interfaces import IMailSentEvent, IMailErrorEvent
from repoze.sendmail.event import MailSentEvent


class TestMailEvents(TestCase):

    def testMailSendEvent(self):
        msgid = '<1234@example.com>'
        m = MailSentEvent(msgid)
        verifyObject(IMailSentEvent, m)
        self.assertEquals(m.messageId, msgid)

    def testMailErrorEvent(self):
        from repoze.sendmail.event import MailErrorEvent
        msgid = '<1234@example.com>'
        error = '550 Relay access denied'
        m = MailErrorEvent(msgid, error)
        verifyObject(IMailErrorEvent, m)
        self.assertEquals(m.messageId, msgid)
        self.assertEquals(m.errorMessage, error)


def test_suite():
    return TestSuite((
        makeSuite(TestMailEvents),
        ))

if __name__ == '__main__':
    unittest.main()
