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
import subprocess
from smtplib import SMTP

try:
    import ssl
except ImportError:  # pragma NO COVER
    HAVE_SSL = False
    SMTP_SSL = None
else:  # pragma NO COVER
    HAVE_SSL = True
    ssl  # pyflakes
    del ssl
    from smtplib import SMTP_SSL

from zope.interface import implementer
from repoze.sendmail.encoding import encode_message
from repoze.sendmail.interfaces import IMailer
from repoze.sendmail._compat import SSLError


@implementer(IMailer)
class SMTPMailer(object):

    smtp = SMTP  # allow replacement for testing.
    smtp_ssl = SMTP_SSL # allow replacement for testing.

    def __init__(self, hostname='localhost', port=25,
                 username=None, password=None,
                 no_tls=False, force_tls=False, ssl=False, debug_smtp=False):
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.force_tls = force_tls
        self.no_tls = no_tls
        self.ssl = ssl
        self.debug_smtp = debug_smtp

    def smtp_factory(self):
        hostname = self.hostname
        port = str(self.port)
        timeout = 10
        if self.ssl:
            if self.smtp_ssl is None:
                raise RuntimeError('No SSL available, cannot send via SSL')
            connection = self.smtp_ssl(hostname, port, timeout=timeout)
        else:
            connection = self.smtp(hostname, port, timeout=timeout)
        connection.set_debuglevel(self.debug_smtp)
        return connection

    def send(self, fromaddr, toaddrs, message):
        if not isinstance(message, Message):
            raise ValueError(
               'Message must be instance of email.message.Message')
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
        have_tls = connection.has_extn('starttls')
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
            # something weird happened while quiting
            connection.close()


@implementer(IMailer)
class SendmailMailer(object):
    """
    Provides for /usr/sbin/sendmail mailing functionality

    Class Defaults ( override in __init__ constructor )
        `sendmail_app`
            sendmail binary location
            '/usr/sbin/sendmail'
        `sendmail_template_no_recipients`
            command line argument used to invoke sendmail when no recipients
            are passed in to `send`
                "%(sendmail_app)s -t -i -f %(sender)s"
        `sendmail_template_recipients`
            command line argument used to invoke sendmail when recipients are
              provided to `send`
                "%(sendmail_app)s -t -i -f %(sender)s %(recipients)"

        all default templates expect/require a sender as sendmail will use the
        system default if no sender is provided

    Standard Sendmail command-line arguments :
        Useful if constructing a new `sendmail_template`
        * for more info see http://linux.die.net/man/8/sendmail.sendmail *
        sendmail [options] recipients
        -f sender | Set the envelope sender address.
                    This is where delivery problems are sent to
                    Sets the name of the ''from'' person (i.e., the envelope
                    sender of the mail). This address may also be used in the
                    From: header if that header is missing during initial
                    submission. The envelope sender address is used as the
                    recipient for delivery status notifications and may also
                    appear in a Return-Path: header. -f should only be used by
                    ''trusted'' users (normally root, daemon, and network) or
                    if the person you are trying to become is the same as the
                    person you are. Otherwise, an X-Authentication-Warning
                    header will be added to the message.
        -i        | When  reading  a message from standard input, don't treat
                    a line with only a . character as the end of input.
                    Ignore dots alone on lines by themselves in incoming
                    messages. This should be set if you are reading data from
                    a file.
        -t        | Read message for recipients. To:, Cc:, and Bcc: lines will
                    be scanned for recipient addresses. The Bcc: line will be
                    deleted before transmission.


    """
    sendmail_app = '/usr/sbin/sendmail'
    sendmail_template = [
        "{sendmail_app}", "-t", "-i", "-f", "{sender}"]

    def __init__(self, sendmail_app=None, sendmail_template=None):
        """see class docstring for details on accepted kwargs"""
        if sendmail_app:
            self.sendmail_app = sendmail_app
        if sendmail_template:
            self.sendmail_template = sendmail_template

    def send(self, fromaddr=None, toaddrs=None, message=None):
        if not isinstance(message, Message):
            raise ValueError(
               'Message must be instance of email.message.Message')
        message = encode_message(message)
        if toaddrs is None:
            toaddrs = []

        args = [arg.format(sendmail_app=self.sendmail_app,
                           sender=fromaddr,
                           recipients=toaddrs)
                for arg in self.sendmail_template] + list(toaddrs)
        p = self._popen(args)
        stdoutdata, stderrdata = p.communicate(message)
        if p.returncode:
            raise subprocess.CalledProcessError(
                "Could not excecute sendmail properly", args)

    def _popen(self, *args, **kw): # pragma NO COVER
        """
        Invoke the actual sendmail subprocess.

        Expects the same call signature as subprocess.Popen.
        """
        kw['stdin'] = subprocess.PIPE
        return subprocess.Popen(*args, **kw) 
