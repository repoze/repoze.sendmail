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
import unittest


class TestSMTPMailer(unittest.TestCase):


    def _getTargetClass(self):
        from repoze.sendmail.mailer import SMTPMailer
        return SMTPMailer

    def _makeOne(self, port=None, ehlo_status=200, extns=set(['starttls',])):
        klass = self._getTargetClass()
        if port is None:
            mailer = klass()
        else:
            mailer = klass('localhost', port)
        smtp = _makeSMTP(ehlo_status, extns)
        mailer.smtp = smtp
        return mailer, smtp

    def test_send(self):
        from email.message import Message
        for run in (1,2):
            if run == 2:
                mailer, smtp = self._makeOne(port=25)
            else:
                mailer, smtp = self._makeOne()
            fromaddr = 'me@example.com'
            toaddrs = ('you@example.com', 'him@example.com')
            msg = Message()
            msg['Headers'] = 'headers'
            msg.set_payload('bodybodybody\n-- \nsig\n')
            mailer.send(fromaddr, toaddrs, msg)
            self.assertEqual(len(smtp._inst), 1)
            inst = smtp._inst[0]
            self.assertEqual(inst.fromaddr, fromaddr)
            self.assertEqual(inst.toaddrs, toaddrs)
            self.assertEqual(inst.msgtext, msg.as_string().encode('ascii'))
            self.assertTrue(inst.quitted)
            self.assertTrue(inst.closed)

    def test_fail_ehlo(self):
        from email.message import Message
        mailer, smtp = self._makeOne(ehlo_status=100)
        fromaddr = 'me@example.com'
        toaddrs = ('you@example.com', 'him@example.com')
        msg = Message()
        self.assertRaises(RuntimeError, mailer.send,
                          fromaddr, toaddrs, msg)

    def test_tls_required_not_available(self):
        from email.message import Message
        mailer, smtp = self._makeOne(extns=set())
        fromaddr = 'me@example.com'
        toaddrs = ('you@example.com', 'him@example.com')
        msg = Message()
        mailer.force_tls = True
        self.assertRaises(RuntimeError, mailer.send,
                          fromaddr, toaddrs, msg)

    def test_send_auth(self):
        from email import message_from_string
        mailer, smtp = self._makeOne()
        fromaddr = 'me@example.com'
        toaddrs = ('you@example.com', 'him@example.com')
        headers = 'Headers: headers'
        body='bodybodybody\n-- \nsig\n'
        msgtext = headers+'\n\n'+body
        msg = message_from_string(msgtext)
        mailer.username = 'foo'
        mailer.password = 'evil'
        mailer.hostname = 'spamrelay'
        mailer.port = 31337
        mailer.send(fromaddr, toaddrs, msg)
        self.assertEqual(len(smtp._inst), 1)
        inst = smtp._inst[0]
        self.assertEqual(inst.username, 'foo')
        self.assertEqual(inst.password, 'evil')
        self.assertEqual(inst.hostname, 'spamrelay')
        self.assertEqual(inst.port, '31337')
        self.assertEqual(inst.fromaddr, fromaddr)
        self.assertEqual(inst.toaddrs, toaddrs)
        self.assertTrue(body.encode('ascii') in inst.msgtext)
        self.assertTrue(headers.encode('ascii') in inst.msgtext)
        self.assertTrue(inst.quitted)
        self.assertTrue(inst.closed)

    def test_send_failQuit(self):
        from email import message_from_string
        mailer, smtp = self._makeOne()
        mailer.smtp.fail_on_quit = True
        try:
            fromaddr = 'me@example.com'
            toaddrs = ('you@example.com', 'him@example.com')
            headers = 'Headers: headers'
            body='bodybodybody\n-- \nsig\n'
            msgtext = headers+'\n\n'+body
            msg = message_from_string(msgtext)
            mailer.send(fromaddr, toaddrs, msg)
            self.assertEqual(len(smtp._inst), 1)
            inst = smtp._inst[0]
            self.assertEqual(inst.fromaddr, fromaddr)
            self.assertEqual(inst.toaddrs, toaddrs)
            self.assertTrue(body.encode('ascii') in inst.msgtext)
            self.assertTrue(headers.encode('ascii') in inst.msgtext)
            self.assertTrue(not inst.quitted)
            self.assertTrue(inst.closed)
        finally:
            mailer.smtp.fail_on_quit = False

    def test_without_debug(self):
        klass = self._getTargetClass()
        mailer = klass(debug_smtp=False)
        mailer.smtp = _makeSMTP()
        connection = mailer.smtp_factory()
        self.assertFalse(connection.debuglevel)

    def test_with_debug(self):
        klass = self._getTargetClass()
        mailer = klass(debug_smtp=True)
        mailer.smtp = _makeSMTP()
        connection = mailer.smtp_factory()
        self.assertTrue(connection.debuglevel)


class TestSMTPMailerWithNoEHLO(TestSMTPMailer):

    def _getTargetClass(self):
        from repoze.sendmail.mailer import SMTPMailer
        return SMTPMailer

    def _makeOne(self, port=None, extns=set(['starttls',])):
        klass = self._getTargetClass()
        if port is None:
            mailer = klass()
        else:
            mailer = klass('localhost', port)
        smtp = _makeSMTPNoEHLO(extns)
        mailer.smtp = smtp
        return mailer, smtp

    def test_send_auth(self):
        from email.message import Message
        mailer, smtp = self._makeOne()
        fromaddr = 'me@example.com'
        toaddrs = ('you@example.com', 'him@example.com')
        msg = Message()
        mailer.username = 'foo'
        mailer.password = 'evil'
        mailer.hostname = 'spamrelay'
        mailer.port = 31337
        self.assertRaises(RuntimeError, mailer.send,
                          fromaddr, toaddrs, msg)

    def test_fail_ehlo(self):
        # This test requires ESMTP, which we're intentionally not enabling
        # here, so pass.
        pass


def _makeSMTP(ehlo_status=200, extns=set(['starttls',])):
    class SMTP(object):
        fail_on_quit = False
        _inst = []

        def __init__(self, h, p):
            self.hostname = h
            self.port = p
            self.quitted = False
            self.closed = False
            self.debuglevel = 0
            SMTP._inst.append(self)

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
            from repoze.sendmail._compat import SSLError
            if self.fail_on_quit:
                raise SSLError("dang")
            self.quitted = True
            self.close()

        def close(self):
            self.closed = True

        def has_extn(self, ext):
            return ext in self.extns

        def ehlo(self):
            self.does_esmtp = True
            return (self.ehlo_status, 'Hello, I am your stupid MTA mock')

        helo = ehlo

        def starttls(self):
            pass

    SMTP.ehlo_status = ehlo_status
    SMTP.extns = extns
    return SMTP


def _makeSMTPNoEHLO(extns):
    SMTP = _makeSMTP(None, extns)
    class SMTPWithNoEHLO(SMTP):
        does_esmtp = False

        def helo(self):
            return (200, 'Hello, I am your stupid MTA mock')

        def ehlo(self):
            return (502, 'I don\'t understand EHLO')
    return SMTPWithNoEHLO


def test_suite():
    return unittest.TestSuite((
        unittest.makeSuite(TestSMTPMailer),
        unittest.makeSuite(TestSMTPMailerWithNoEHLO),
    ))
