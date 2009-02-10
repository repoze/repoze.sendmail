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
"""Tests for mailers.

$Id: test_mailer.py 92756 2008-11-03 12:50:08Z adamg $
"""

from StringIO import StringIO
from zope.interface.verify import verifyObject
from repoze.sendmail.interfaces import ISMTPMailer
from repoze.sendmail.mailer import SMTPMailer
import socket
import unittest


class TestSMTPMailer(unittest.TestCase):

    def setUp(self, port=None):
        global SMTP
        class SMTP(object):

            fail_on_quit = False

            def __init__(myself, h, p):
                myself.hostname = h
                myself.port = p
                myself.quitted = False
                myself.closed = False
                if type(p) == type(u""):
                    raise socket.error("Int or String expected")
                self.smtp = myself

            def sendmail(self, f, t, m):
                self.fromaddr = f
                self.toaddrs = t
                self.msgtext = m

            def login(self, username, password):
                self.username = username
                self.password = password

            def quit(self):
                if self.fail_on_quit:
                    raise socket.sslerror("dang")
                self.quitted = True
                self.close()

            def close(self):
                self.closed = True

            def has_extn(self, ext):
                return True

            def ehlo(self):
                self.does_esmtp = True
                return (200, 'Hello, I am your stupid MTA mock')

            def starttls(self):
                pass


        if port is None:
            self.mailer = SMTPMailer()
        else:
            self.mailer = SMTPMailer(u'localhost', port)
        self.mailer.smtp = SMTP

    def test_interface(self):
        verifyObject(ISMTPMailer, self.mailer)

    def test_send(self):
        for run in (1,2):
            if run == 2:
                self.setUp(u'25')
            fromaddr = 'me@example.com'
            toaddrs = ('you@example.com', 'him@example.com')
            msgtext = 'Headers: headers\n\nbodybodybody\n-- \nsig\n'
            self.mailer.send(fromaddr, toaddrs, msgtext)
            self.assertEquals(self.smtp.fromaddr, fromaddr)
            self.assertEquals(self.smtp.toaddrs, toaddrs)
            self.assertEquals(self.smtp.msgtext, msgtext)
            self.assert_(self.smtp.quitted)
            self.assert_(self.smtp.closed)

    def test_send_auth(self):
        fromaddr = 'me@example.com'
        toaddrs = ('you@example.com', 'him@example.com')
        msgtext = 'Headers: headers\n\nbodybodybody\n-- \nsig\n'
        self.mailer.username = 'foo'
        self.mailer.password = 'evil'
        self.mailer.hostname = 'spamrelay'
        self.mailer.port = 31337
        self.mailer.send(fromaddr, toaddrs, msgtext)
        self.assertEquals(self.smtp.username, 'foo')
        self.assertEquals(self.smtp.password, 'evil')
        self.assertEquals(self.smtp.hostname, 'spamrelay')
        self.assertEquals(self.smtp.port, '31337')
        self.assertEquals(self.smtp.fromaddr, fromaddr)
        self.assertEquals(self.smtp.toaddrs, toaddrs)
        self.assertEquals(self.smtp.msgtext, msgtext)
        self.assert_(self.smtp.quitted)
        self.assert_(self.smtp.closed)

    def test_send_failQuit(self):
        self.mailer.smtp.fail_on_quit = True
        try:
            fromaddr = 'me@example.com'
            toaddrs = ('you@example.com', 'him@example.com')
            msgtext = 'Headers: headers\n\nbodybodybody\n-- \nsig\n'
            self.mailer.send(fromaddr, toaddrs, msgtext)
            self.assertEquals(self.smtp.fromaddr, fromaddr)
            self.assertEquals(self.smtp.toaddrs, toaddrs)
            self.assertEquals(self.smtp.msgtext, msgtext)
            self.assert_(not self.smtp.quitted)
            self.assert_(self.smtp.closed)
        finally:
            self.mailer.smtp.fail_on_quit = False


class TestSMTPMailerWithNoEHLO(TestSMTPMailer):

    def setUp(self, port=None):

        class SMTPWithNoEHLO(SMTP):
            does_esmtp = False

            def __init__(myself, h, p):
                myself.hostname = h
                myself.port = p
                myself.quitted = False
                myself.closed = False
                if type(p) == type(u""):
                    raise socket.error("Int or String expected")
                self.smtp = myself

            def helo(self):
                return (200, 'Hello, I am your stupid MTA mock')

            def ehlo(self):
                return (502, 'I don\'t understand EHLO')


        if port is None:
            self.mailer = SMTPMailer()
        else:
            self.mailer = SMTPMailer(u'localhost', port)
        self.mailer.smtp = SMTPWithNoEHLO

    def test_send_auth(self):
        # This test requires ESMTP, which we're intentionally not enabling
        # here, so pass.
        pass

def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestSMTPMailer))
    suite.addTest(unittest.makeSuite(TestSMTPMailerWithNoEHLO))
    return suite


if __name__ == '__main__':
    unittest.main()
