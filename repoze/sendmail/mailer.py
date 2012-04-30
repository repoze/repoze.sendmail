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
from email.message import Message
from smtplib import SMTP
try:
    from socket import ssl
except ImportError: #pragma NO COVER
    HAVE_SSL = False
else: #pragma NO COVER
    HAVE_SSL = True
    del ssl

from zope.interface import implementer
from repoze.sendmail.encoding import encode_message
from repoze.sendmail.interfaces import IMailer
from repoze.sendmail._compat import SSLError


class SMTPMailer(object):

    smtp = SMTP  #allow replacement for testing.

    def __init__(self, hostname='localhost', port=25,
                 username=None, password=None,
                 no_tls=False, force_tls=False, debug_smtp=False):
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.force_tls = force_tls
        self.no_tls = no_tls
        self.debug_smtp = debug_smtp

    def smtp_factory(self):
        connection = self.smtp(self.hostname, str(self.port))
        connection.set_debuglevel(self.debug_smtp)
        return connection

    def send(self, fromaddr, toaddrs, message):
        assert isinstance(message, Message), \
               'Message must be instance of email.message.Message'
        message = encode_message(message)

        connection = self.smtp_factory()

        # send EHLO
        code, response = connection.ehlo()
        if code < 200 or code >= 300:
            code, response = connection.helo()
            if code < 200 or code >= 300:
                raise RuntimeError(
                        'Error sending HELO to the SMTP server '
                        '(code=%s, response=%s)' % (code, response))

        # encryption support
        have_tls =  connection.has_extn('starttls')
        if not have_tls and self.force_tls:
            raise RuntimeError('TLS is not available but TLS is required')

        if have_tls and HAVE_SSL and not self.no_tls:
            connection.starttls()
            connection.ehlo()

        if connection.does_esmtp:
            if self.username is not None and self.password is not None:
                connection.login(self.username, self.password)
        elif self.username:
            raise RuntimeError(
                    'Mailhost does not support ESMTP but a username '
                    'is configured')

        connection.sendmail(fromaddr, toaddrs, message)
        try:
            connection.quit()
        except SSLError:
            #something weird happened while quiting
            connection.close()

# BBB Python 2.5 compat
SMTPMailer = implementer(IMailer)(SMTPMailer)
