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

import socket
from smtplib import SMTP

try:
    from ssl import SSLError
except ImportError: # pragma: no cover
    # BBB Python 2.5
    from socket import sslerror as SSLError

from zope.interface import implementer
from repoze.sendmail.interfaces import IMailer
from repoze.sendmail import encoding

have_ssl = hasattr(socket, 'ssl')


class SMTPMailer(object):

    smtp = SMTP

    def __init__(self, hostname='localhost', port=25,
                 username=None, password=None, no_tls=False, force_tls=False, debug_smtp=False):
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
        message = encoding.encode_message(message)

        connection = self.smtp_factory()

        # send EHLO
        code, response = connection.ehlo()
        if code < 200 or code >= 300:
            code, response = connection.helo()
            if code < 200 or code >= 300:
                raise RuntimeError('Error sending HELO to the SMTP server '
                                   '(code=%s, response=%s)' % (code, response))

        # encryption support
        have_tls =  connection.has_extn('starttls')
        if not have_tls and self.force_tls:
            raise RuntimeError('TLS is not available but TLS is required')

        if have_tls and have_ssl and not self.no_tls:
            connection.starttls()
            connection.ehlo()

        if connection.does_esmtp:
            if self.username is not None and self.password is not None:
                connection.login(self.username, self.password)
        elif self.username:
            raise RuntimeError('Mailhost does not support ESMTP but a username '
                                'is configured')

        connection.sendmail(fromaddr, toaddrs, message)
        try:
            connection.quit()
        except SSLError:
            #something weird happened while quiting
            connection.close()

# BBB Python 2.5 compat
SMTPMailer = implementer(IMailer)(SMTPMailer)
