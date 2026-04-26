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
import email
import ssl
import subprocess
from email import message as email_message

import pytest

from repoze.sendmail import mailer as mailer_module

SMTP_OTHER_HOSTNAME = "smtp.example.com"
SMTP_OTHER_PORT = 2225
SMTP_USER_NAME = "phreddy"
SMTP_PASSWORD = "m3rcur7"

FROM_ADDR = "me@example.com"
TO_ADDRS = ("you@example.com", "him@example.com")
HEADERS = "Headers: headers"
BODY = "bodybodybody\n-- \nsig\n"

# Fixture casees
# - SMTPMailer()
# - SMTPMailer("localhost", port)


EXTN_ONLY_STARTTLS = frozenset(["starttls"])


def _makeSMTP(ehlo_status=200, extns=EXTN_ONLY_STARTTLS):
    class SMTP:
        is_factory = True
        fail_on_quit = False
        _inst = []

        def __init__(self, h, p, **params):
            self.hostname = h
            self.port = p
            self.quitted = False
            self.closed = False
            self.debuglevel = 0
            self.params = params
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
            if self.fail_on_quit:
                raise ssl.SSLError("dang")
            self.quitted = True
            self.close()

        def close(self):
            self.closed = True

        def has_extn(self, ext):
            return ext in self.extns

        def ehlo(self):
            self.does_esmtp = True
            return (self.ehlo_status, "Hello, I am your stupid MTA mock")

        helo = ehlo

        def starttls(self):
            pass

    SMTP.ehlo_status = ehlo_status
    SMTP.extns = extns
    return SMTP


def _makeSMTPNoEHLO(extns=EXTN_ONLY_STARTTLS):
    SMTP = _makeSMTP(None, extns)

    class SMTPWithNoEHLO(SMTP):
        does_esmtp = False

        def helo(self):
            return (200, "Hello, I am your stupid MTA mock")

        def ehlo(self):
            return (502, "I don't understand EHLO")

    return SMTPWithNoEHLO


@pytest.fixture(params=[_makeSMTP, _makeSMTPNoEHLO])
def smtp_factory_func(request):
    return request.param


@pytest.mark.parametrize(
    "w_kwargs, exp_attrs",
    [
        (
            {},
            {
                "hostname": "localhost",
                "port": 25,
                "username": None,
                "password": None,
                "no_tls": False,
                "force_tls": False,
                "ssl": False,
                "debug_smtp": False,
            },
        ),
        ({"hostname": SMTP_OTHER_HOSTNAME, "port": SMTP_OTHER_PORT}, None),
        ({"username": SMTP_USER_NAME, "password": SMTP_PASSWORD}, None),
        ({"force_tls": True}, None),
        ({"no_tls": True}, None),
        ({"ssl": True}, None),
        ({"debug_smtp": True}, None),
    ],
)
def test_smtpmailer_ctor(w_kwargs, exp_attrs):
    found = mailer_module.SMTPMailer(**w_kwargs)

    if exp_attrs is None:
        exp_attrs = w_kwargs

    for attr_name, exp_value in exp_attrs.items():
        assert getattr(found, attr_name) == exp_value


def test_smtpmailer_smtp_factory_ssl_required_not_available():
    # Raises before calling the factory, so we don't parametrize it.
    mailer = mailer_module.SMTPMailer(ssl=True)
    mailer.smtp_ssl = None

    with pytest.raises(mailer_module.SSL_NotAvailable):
        mailer.smtp_factory()


def test_smtpmailer_smtp_factory_ssl_required_and_available(smtp_factory_func):
    mailer = mailer_module.SMTPMailer(ssl=True)
    mailer.smtp_ssl = smtp_factory_func(extns=set())

    result = mailer.smtp_factory()

    assert result.is_factory


def test_smtpmailer_smtp_factory_without_debug():
    mailer = mailer_module.SMTPMailer(debug_smtp=False)
    mailer.smtp = _makeSMTP()

    connection = mailer.smtp_factory()

    assert not connection.debuglevel


def test_smtpmailer_smtp_factory_with_debug():
    mailer = mailer_module.SMTPMailer(debug_smtp=True)
    mailer.smtp = _makeSMTP()

    connection = mailer.smtp_factory()

    assert connection.debuglevel


def test_smtpmailer_send_w_non_message(smtp_factory_func):
    mailer = mailer_module.SMTPMailer()
    mailer.smtp = smtp_factory_func()

    with pytest.raises(mailer_module.NotAnEmailMessage):
        mailer.send(FROM_ADDR, TO_ADDRS, b"")


def test_smtpmailer_send_fail_ehlo():
    # This test requires ESMTP, so we don't parametrize the factory
    msg = email_message.Message()
    mailer = mailer_module.SMTPMailer()
    mailer.smtp = _makeSMTP(ehlo_status=100, extns=set())

    with pytest.raises(mailer_module.EHLO_Error):
        mailer.send(FROM_ADDR, TO_ADDRS, msg)


def test_smtpmailer_send_tls_required_not_available(smtp_factory_func):
    msg = email_message.Message()
    mailer = mailer_module.SMTPMailer(force_tls=True)
    mailer.smtp = smtp_factory_func(extns=set())

    with pytest.raises(mailer_module.TLS_NotAvailable):
        mailer.send(FROM_ADDR, TO_ADDRS, msg)


def test_smtpmailer_send_tls_available_but_disabled(smtp_factory_func):
    msg = email_message.Message()
    mailer = mailer_module.SMTPMailer(no_tls=True)
    mailer.smtp = smtp_factory_func(extns=set())

    mailer.send(FROM_ADDR, TO_ADDRS, msg)  # no raise


def test_smtpmailer_send_auth_w_ehlo():
    msgtext = HEADERS + "\n\n" + BODY
    msg = email.message_from_string(msgtext)

    mailer = mailer_module.SMTPMailer()
    mailer.smtp = _makeSMTP()
    mailer.username = "foo"
    mailer.password = "evil"
    mailer.hostname = "spamrelay"
    mailer.port = 31337

    mailer.send(FROM_ADDR, TO_ADDRS, msg)

    (inst,) = mailer.smtp._inst
    assert inst.username == "foo"
    assert inst.password == "evil"
    assert inst.hostname == "spamrelay"
    assert inst.port == "31337"
    assert inst.fromaddr == FROM_ADDR
    assert inst.toaddrs == TO_ADDRS
    assert BODY.encode("ascii") in inst.msgtext
    assert HEADERS.encode("ascii") in inst.msgtext
    assert inst.quitted
    assert inst.closed


def test_smtpmailer_send_auth_wo_ehlo():
    msg = email_message.Message()

    mailer = mailer_module.SMTPMailer()
    mailer.smtp = _makeSMTPNoEHLO()
    mailer.username = "foo"
    mailer.password = "evil"
    mailer.hostname = "spamrelay"
    mailer.port = 31337

    with pytest.raises(mailer_module.ESMTP_NotSupported):
        mailer.send(FROM_ADDR, TO_ADDRS, msg)


def test_smtpmailer_send_fail_inside_quit(smtp_factory_func):
    msgtext = HEADERS + "\n\n" + BODY
    msg = email.message_from_string(msgtext)

    mailer = mailer_module.SMTPMailer()
    mailer.smtp = smtp_factory_func()
    mailer.smtp.fail_on_quit = True

    try:
        mailer.send(FROM_ADDR, TO_ADDRS, msg)
    finally:
        mailer.smtp.fail_on_quit = False

    (inst,) = mailer.smtp._inst
    assert inst.fromaddr == FROM_ADDR
    assert inst.toaddrs == TO_ADDRS
    assert BODY.encode("ascii") in inst.msgtext
    assert HEADERS.encode("ascii") in inst.msgtext
    assert not inst.quitted
    assert inst.closed


class SendmailMailerStub(mailer_module.SendmailMailer):
    popens = ()

    def __init__(self, *args, **kw):
        self.returncode = kw.pop("returncode", 0)
        super().__init__(*args, **kw)

    def _popen(self, *args, **kw):
        kw["returncode"] = self.returncode
        p = PopenStub(*args, **kw)
        self.popens += (p,)
        return p


def test_sendmailmailer_send_w_non_message():
    mailer = SendmailMailerStub()

    with pytest.raises(mailer_module.NotAnEmailMessage):
        mailer.send(FROM_ADDR, TO_ADDRS, b"")


def test_sendmailmailer_send_commandline_recipients():
    msg = email_message.Message()
    msg["Headers"] = "headers"
    msg.set_payload("bodybodybody\n-- \nsig\n")
    mailer = SendmailMailerStub()

    mailer.send(FROM_ADDR, TO_ADDRS, msg)

    assert mailer.popens[0].args[0] == [
        "/usr/sbin/sendmail",
        "-t",
        "-i",
        "-f",
        "me@example.com",
        "you@example.com",
        "him@example.com",
    ]


def test_sendmailmailer_send_header_recipients():
    msg = email_message.Message()
    msg["To"] = ",".join(TO_ADDRS)
    msg.set_payload("bodybodybody\n-- \nsig\n")

    mailer = SendmailMailerStub(
        sendmail_app="/usr/local/sbin/sendmail",
        sendmail_template=["{sendmail_app}", "-t", "-f", "{sender}"],
        returncode=1,
    )

    with pytest.raises(subprocess.CalledProcessError):
        mailer.send(FROM_ADDR, None, msg)

    assert mailer.popens[0].args[0] == [
        "/usr/local/sbin/sendmail",
        "-t",
        "-f",
        "me@example.com",
    ]


class PopenStub:
    def __init__(self, *args, **kw):
        self.args = args
        self.kw = kw
        self.inputs = []
        self.returncode = kw.get("returncode", 0)

    def communicate(self, input):
        # 'input' must be bytes.  See:
        # http://docs.python.org/3/library/subprocess.html
        #                                    #subprocess.Popen.communicate
        assert isinstance(input, bytes)
        self.inputs.append(input)
        return "", ""
