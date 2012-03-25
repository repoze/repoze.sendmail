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

from zope.interface.verify import verifyObject
from repoze.sendmail.mailer import SMTPMailer
import email
import unittest

try: 
    from ssl import SSLError
except ImportError: # pragma: no cover
    # BBB Python 2.5
    from socket import sslerror as SSLError


class TestSMTPMailer(unittest.TestCase):

    def setUp(self, port=None):
        self.ehlo_status = 200
        self.extns = set(['starttls',])
        global SMTP
        class SMTP(object):
            fail_on_quit = False

            def __init__(myself, h, p):
                myself.hostname = h
                myself.port = p
                myself.quitted = False
                myself.closed = False
                myself.debuglevel = 0
                self.smtp = myself

            def set_debuglevel(self, lvl):
                self.debuglevel = bool(lvl)

            def sendmail(self, f, t, m):
                self.fromaddr = f
                self.toaddrs = t
                self.msgtext = m

            def login(self, username, password):
                self.username = username
                self.password = password

            def quit(self):
                if self.fail_on_quit:
                    raise SSLError("dang")
                self.quitted = True
                self.close()

            def close(self):
                self.closed = True

            def has_extn(myself, ext):
                return ext in self.extns

            def ehlo(myself):
                myself.does_esmtp = True
                return (self.ehlo_status, 'Hello, I am your stupid MTA mock')

            helo = ehlo

            def starttls(self):
                pass


        if port is None:
            self.mailer = SMTPMailer()
        else:
            self.mailer = SMTPMailer('localhost', port)
        self.mailer.smtp = SMTP

    def test_send(self):
        from email.message import Message
        for run in (1,2):
            if run == 2:
                self.setUp('25')
            fromaddr = 'me@example.com'
            toaddrs = ('you@example.com', 'him@example.com')
            msg = Message()
            msg['Headers'] = 'headers'
            msg.set_payload('bodybodybody\n-- \nsig\n')
            self.mailer.send(fromaddr, toaddrs, msg)
            self.assertEqual(self.smtp.fromaddr, fromaddr)
            self.assertEqual(self.smtp.toaddrs, toaddrs)
            self.assertEqual(
                self.smtp.msgtext, msg.as_string().encode('ascii'))
            self.assertTrue(self.smtp.quitted)
            self.assertTrue(self.smtp.closed)

    def test_fail_ehlo(self):
        from email.message import Message
        fromaddr = 'me@example.com'
        toaddrs = ('you@example.com', 'him@example.com')
        msg = Message()
        self.ehlo_status = 100
        self.assertRaises(RuntimeError, self.mailer.send,
                          fromaddr, toaddrs, msg)

    def test_tls_required_not_available(self):
        from email.message import Message
        fromaddr = 'me@example.com'
        toaddrs = ('you@example.com', 'him@example.com')
        msg = Message()
        self.extns.remove('starttls')
        self.mailer.force_tls = True
        self.assertRaises(RuntimeError, self.mailer.send,
                          fromaddr, toaddrs, msg)

    def test_send_auth(self):
        fromaddr = 'me@example.com'
        toaddrs = ('you@example.com', 'him@example.com')
        headers = 'Headers: headers'
        body='bodybodybody\n-- \nsig\n'
        msgtext = headers+'\n\n'+body
        msg = email.message_from_string(msgtext)
        self.mailer.username = 'foo'
        self.mailer.password = 'evil'
        self.mailer.hostname = 'spamrelay'
        self.mailer.port = 31337
        self.mailer.send(fromaddr, toaddrs, msg)
        self.assertEqual(self.smtp.username, 'foo')
        self.assertEqual(self.smtp.password, 'evil')
        self.assertEqual(self.smtp.hostname, 'spamrelay')
        self.assertEqual(self.smtp.port, '31337')
        self.assertEqual(self.smtp.fromaddr, fromaddr)
        self.assertEqual(self.smtp.toaddrs, toaddrs)
        self.assertTrue(body.encode('ascii') in self.smtp.msgtext)
        self.assertTrue(headers.encode('ascii') in self.smtp.msgtext)
        self.assertTrue(self.smtp.quitted)
        self.assertTrue(self.smtp.closed)

    def test_send_failQuit(self):
        self.mailer.smtp.fail_on_quit = True
        try:
            fromaddr = 'me@example.com'
            toaddrs = ('you@example.com', 'him@example.com')
            headers = 'Headers: headers'
            body='bodybodybody\n-- \nsig\n'
            msgtext = headers+'\n\n'+body
            msg = email.message_from_string(msgtext)
            self.mailer.send(fromaddr, toaddrs, msg)
            self.assertEqual(self.smtp.fromaddr, fromaddr)
            self.assertEqual(self.smtp.toaddrs, toaddrs)
            self.assertTrue(body.encode('ascii') in self.smtp.msgtext)
            self.assertTrue(headers.encode('ascii') in self.smtp.msgtext)
            self.assertTrue(not self.smtp.quitted)
            self.assertTrue(self.smtp.closed)
        finally:
            self.mailer.smtp.fail_on_quit = False

class TestSMTPMailerWithNoEHLO(TestSMTPMailer):

    def setUp(self, port=None):
        self.extns = set(['starttls',])

        class SMTPWithNoEHLO(SMTP):
            does_esmtp = False

            def __init__(myself, h, p):
                myself.hostname = h
                myself.port = p
                myself.quitted = False
                myself.closed = False
                self.smtp = myself

            def helo(self):
                return (200, 'Hello, I am your stupid MTA mock')

            def ehlo(self):
                return (502, 'I don\'t understand EHLO')


        if port is None:
            self.mailer = SMTPMailer()
        else:
            self.mailer = SMTPMailer('localhost', port)
        self.mailer.smtp = SMTPWithNoEHLO

    def test_send_auth(self):
        from email.message import Message
        fromaddr = 'me@example.com'
        toaddrs = ('you@example.com', 'him@example.com')
        msg = Message()
        self.mailer.username = 'foo'
        self.mailer.password = 'evil'
        self.mailer.hostname = 'spamrelay'
        self.mailer.port = 31337
        self.assertRaises(RuntimeError, self.mailer.send,
                          fromaddr, toaddrs, msg)

    def test_fail_ehlo(self):
        # This test requires ESMTP, which we're intentionally not enabling
        # here, so pass.
        pass

class TestSMTPMailerWithSMTPDebug(unittest.TestCase):

    def setUp(self, debug_smtp=True):
        self.mailer = SMTPMailer(debug_smtp=debug_smtp)
        self.mailer.smtp = SMTP

    def test_without_debug(self):
        self.setUp(False)
        connection = self.mailer.smtp_factory()
        self.assertFalse(connection.debuglevel)

    def test_with_debug(self):
        connection = self.mailer.smtp_factory()
        self.assertTrue(connection.debuglevel)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestSMTPMailer))
    suite.addTest(unittest.makeSuite(TestSMTPMailerWithNoEHLO))
    suite.addTest(unittest.makeSuite(TestSMTPMailerWithSMTPDebug))
    return suite
