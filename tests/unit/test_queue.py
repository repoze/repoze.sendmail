import io
import os.path
import smtplib
from email import message as email_message  # Message
from unittest import mock

import pytest
import transaction
from zope.interface import implementer

from repoze.sendmail import delivery as delivery_module
from repoze.sendmail import interfaces as interfaces_module
from repoze.sendmail import maildir as maildir_module  # Maildir
from repoze.sendmail import queue as queue_module
from tests.unit.test_delivery import MaildirStub
from tests.unit.test_delivery import _makeMailerStub


class LoggerStub:
    def __init__(self):
        self.infos = []
        self.errors = []

    def error(self, msg, *args, **kwargs):
        self.errors.append((msg, args, kwargs))

    def info(self, msg, *args, **kwargs):
        self.infos.append((msg, args, kwargs))


class BizzarreMailError(IOError):
    def __init__(self):
        super().__init__("bad things happened while sending mail")


@implementer(interfaces_module.IMailer)
class BrokenMailerStub:
    def __init__(self, *args, **kw):
        pass

    def send(self, fromaddr, toaddrs, message):
        raise BizzarreMailError()


@implementer(interfaces_module.IMailer)
class SMTPResponseExceptionMailerStub:
    def __init__(self, code):
        self.code = code

    def send(self, fromaddr, toaddrs, message):
        raise smtplib.SMTPResponseException(self.code, "Serious Error")


@pytest.fixture
def queue_processor():
    qp = queue_module.QueueProcessor(
        _makeMailerStub(), "/foo/bar/baz", MaildirStub
    )
    qp.log = LoggerStub()
    return qp


def test_qp_parseMessage(queue_processor):
    hdr = (
        "X-Actually-From: foo@example.com\n"
        "X-Actually-To: bar@example.com, baz@example.com\n"
    )
    msg = "Header: value\n\nBody\n"

    f, t, m = queue_processor._parseMessage(io.StringIO(hdr + msg))

    assert f == "foo@example.com"
    assert t == ("bar@example.com", "baz@example.com")
    assert m.as_string() == msg


def test_delivery(tmp_path, queue_processor):
    filename = tmp_path / "message"
    filename.write_bytes(
        b"X-Actually-From: foo@example.com\n"
        + b"X-Actually-To: bar@example.com, baz@example.com\n"
        + b"Header: value\n\nBody\n"
    )
    queue_processor.maildir.files.append(str(filename))

    queue_processor.send_messages()

    sent_message = queue_processor.mailer.sent_messages[0]

    assert sent_message[0] == "foo@example.com"
    assert sent_message[1] == ("bar@example.com", "baz@example.com")
    assert sent_message[2].as_string() == "Header: value\n\nBody\n"
    assert not filename.exists()

    (
        (
            msg,
            args,
            info,
        ),
    ) = queue_processor.log.infos
    assert msg == "Mail from %s to %s sent."
    assert args == ("foo@example.com", "bar@example.com, baz@example.com")
    assert info == {}


def test_error_logging(tmp_path, queue_processor):
    queue_processor.mailer = BrokenMailerStub()
    filename = tmp_path / "message"
    filename.write_bytes(
        b"X-Actually-From: foo@example.com\n"
        + b"X-Actually-To: bar@example.com, baz@example.com\n"
        + b"Header: value\n\nBody\n"
    )
    queue_processor.maildir.files.append(str(filename))

    queue_processor.send_messages()

    (
        (
            msg,
            args,
            info,
        ),
    ) = queue_processor.log.errors
    assert msg == "Error while sending mail from %s to %s."
    assert args == ("foo@example.com", "bar@example.com, baz@example.com")
    assert info == {"exc_info": 1}


def test_error_logging_no_addrs(tmp_path, queue_processor):
    queue_processor.mailer = BrokenMailerStub()
    filename = tmp_path / "message"
    filename.write_bytes(b"Header: value\n\nBody\n")
    queue_processor.maildir.files.append(str(filename))

    queue_processor.send_messages()

    (
        (
            msg,
            args,
            info,
        ),
    ) = queue_processor.log.errors
    assert msg == "Error while sending mail : %s "
    assert args == (str(filename),)
    assert info == {"exc_info": True}


def test_smtp_response_error_transient(tmp_path, queue_processor):
    # Test a transient error
    queue_processor.mailer = SMTPResponseExceptionMailerStub(451)
    filename = tmp_path / "message"
    filename.write_bytes(
        b"X-Actually-From: foo@example.com\n"
        + b"X-Actually-To: bar@example.com, baz@example.com\n"
        + b"Header: value\n\nBody\n"
    )
    queue_processor.maildir.files.append(str(filename))

    queue_processor.send_messages()

    # File must remain were it was, so it will be retried
    assert filename.exists()

    (
        (
            msg,
            args,
            info,
        ),
    ) = queue_processor.log.errors
    assert msg == "Error while sending mail from %s to %s."
    assert args == ("foo@example.com", "bar@example.com, baz@example.com")
    assert info == {"exc_info": 1}


def test_smtp_response_error_transient_ignore_exc(tmp_path, queue_processor):
    # Test a transient error but ignore exception
    queue_processor.ignore_transient = True
    queue_processor.mailer = SMTPResponseExceptionMailerStub(451)
    filename = tmp_path / "message"
    filename.write_bytes(
        b"X-Actually-From: foo@example.com\n"
        + b"X-Actually-To: bar@example.com, baz@example.com\n"
        + b"Header: value\n\nBody\n"
    )
    queue_processor.maildir.files.append(str(filename))

    queue_processor.send_messages()

    # File must remain were it was, so it will be retried
    assert filename.exists()

    # Transient errors ignored, so log should be empty
    assert queue_processor.log.errors == []


def test_smtp_response_error_permanent(tmp_path, queue_processor):
    # Test a permanent error
    queue_processor.mailer = SMTPResponseExceptionMailerStub(550)
    filename = tmp_path / "message"
    filename.write_bytes(
        b"X-Actually-From: foo@example.com\n"
        + b"X-Actually-To: bar@example.com, baz@example.com\n"
        + b"Header: value\n\nBody\n"
    )
    queue_processor.maildir.files.append(str(filename))

    queue_processor.send_messages()

    # File must be moved aside
    assert not filename.exists()
    rejected = tmp_path / ".rejected-message"
    assert rejected.exists()

    (
        (
            msg,
            args,
            info,
        ),
    ) = queue_processor.log.errors
    assert msg == "Discarding email from %s to %s due to a permanent error: %s"
    assert args == (
        "foo@example.com",
        "bar@example.com, baz@example.com",
        (550, "Serious Error"),
    )
    assert info == {}


def test_concurrent_delivery(tmp_path, queue_processor):
    # Attempt to send message
    filename = tmp_path / "message"

    filename.write_bytes(
        b"X-Actually-From: foo@example.com\n"
        + b"X-Actually-To: bar@example.com, baz@example.com\n"
        + b"Header: value\n\nBody\n"
    )

    queue_processor.maildir.files.append(str(filename))

    # Trick processor into thinking message is being delivered by
    # another process.
    head, tail = filename.parent, filename.name
    tmp_filename = head / (".sending-" + str(tail))
    tmp_filename.hardlink_to(filename)

    try:
        queue_processor.send_messages()
    finally:
        tmp_filename.unlink()

    assert filename.exists()
    assert queue_processor.mailer.sent_messages == []
    assert queue_processor.log.infos == []


def test_concurrent_delivery_w_old_file(tmp_path, queue_processor):
    # Attempt to send message
    filename = tmp_path / "message"

    filename.write_bytes(
        b"X-Actually-From: foo@example.com\n"
        + b"X-Actually-To: bar@example.com, baz@example.com\n"
        + b"Header: value\n\nBody\n"
    )

    queue_processor.maildir.files.append(str(filename))

    # Trick processor into thinking message is being delivered by
    # another process.
    head, tail = filename.parent, filename.name
    tmp_filename = head / (".sending-" + str(tail))
    tmp_filename.hardlink_to(filename)

    os.utime(str(tmp_filename), (1, 1))  # mtime/utime 1970-01-01T00:00:01Z

    queue_processor.send_messages()

    sent_message = queue_processor.mailer.sent_messages[0]
    assert sent_message[0] == "foo@example.com"
    assert sent_message[1] == ("bar@example.com", "baz@example.com")
    assert sent_message[2].as_string() == "Header: value\n\nBody\n"

    assert not filename.exists()

    (
        (
            msg,
            args,
            info,
        ),
    ) = queue_processor.log.infos
    assert msg == "Mail from %s to %s sent."
    assert args == ("foo@example.com", "bar@example.com, baz@example.com")
    assert info == {}


def test_console_app_cli_args_ws_simple_arg_ok(tmp_path):
    # Simplest case that works
    cmdline = f"qp {tmp_path}"

    app = queue_module.ConsoleApp(cmdline.split())

    assert app.script_name == "qp"
    assert not app._error
    assert app.queue_path == str(tmp_path)
    assert app.hostname == "localhost"
    assert app.port == 25
    assert app.username is None
    assert app.password is None
    assert not app.force_tls
    assert not app.no_tls
    assert not app.debug_smtp


def test_console_app_cli_args_w_simple_error():
    # Simplest case that doesn't work
    cmdline = "qp"

    with mock.patch("repoze.sendmail.queue._log_error") as logged:
        app = queue_module.ConsoleApp(cmdline.split())

    assert app.script_name == "qp"
    assert app._error
    assert app.queue_path is None
    assert app.hostname == "localhost"
    assert app.port == 25
    assert app.username is None
    assert app.password is None
    assert not app.force_tls
    assert not app.no_tls
    assert not app.debug_smtp

    assert len(logged.call_args_list) == 1

    app.main()


def test_console_app_cli_args_w_full_monty(tmp_path):
    # Use (almost) all of the options
    cmdline = f"""qp --hostname foo --port 75
                    --username chris --password rossi --force-tls
                    --debug-smtp --ssl
                    {tmp_path}"""

    app = queue_module.ConsoleApp(cmdline.split())

    assert app.script_name == "qp"
    assert not app._error
    assert app.queue_path == str(tmp_path)
    assert app.hostname == "foo"
    assert app.port == 75
    assert app.username == "chris"
    assert app.password == "rossi"
    assert app.force_tls
    assert app.ssl
    assert not app.no_tls
    assert app.debug_smtp


def test_console_app_cli_args_w_username_no_password(tmp_path):
    # Test username without password
    cmdline = f"qp --username chris {tmp_path}"

    with mock.patch("repoze.sendmail.queue._log_error") as logged:
        app = queue_module.ConsoleApp(cmdline.split())

    assert app._error
    assert len(logged.call_args_list) == 1


def test_console_app_cli_args_w_force_tls_no_tls(tmp_path):
    # Test force_tls and no_tls
    cmdline = f"qp --force-tls --no-tls {tmp_path}"

    with mock.patch("repoze.sendmail.queue._log_error") as logged:
        app = queue_module.ConsoleApp(cmdline.split())

    assert app._error
    assert len(logged.call_args_list) == 1


def test_console_app_cli_args_w_hostname_no_hostname(tmp_path):
    cmdline = f"qp {tmp_path} --hostname"

    with mock.patch("repoze.sendmail.queue._log_error") as logged:
        app = queue_module.ConsoleApp(cmdline.split())

    assert app._error
    assert len(logged.call_args_list) == 1


def testconsole_app_cli_args_ws_port_no_port(tmp_path):
    cmdline = f"qp {tmp_path} --port"

    with mock.patch("repoze.sendmail.queue._log_error") as logged:
        app = queue_module.ConsoleApp(cmdline.split())

    assert app._error
    assert len(logged.call_args_list) == 1


def test_console_app_cli_args_w_bad_port(tmp_path):
    cmdline = f"qp {tmp_path} --port foo"

    with mock.patch("repoze.sendmail.queue._log_error") as logged:
        app = queue_module.ConsoleApp(cmdline.split())

    assert app._error
    assert len(logged.call_args_list) == 1


def test_console_app_cli_args_w_username_no_username(tmp_path):
    cmdline = f"qp {tmp_path} --username"

    with mock.patch("repoze.sendmail.queue._log_error") as logged:
        app = queue_module.ConsoleApp(cmdline.split())

    assert app._error
    assert len(logged.call_args_list) == 1


def test_console_app_cli_args_w_password_no_password(tmp_path):
    cmdline = f"qp {tmp_path} --password"

    with mock.patch("repoze.sendmail.queue._log_error") as logged:
        app = queue_module.ConsoleApp(cmdline.split())

    assert app._error
    assert len(logged.call_args_list) == 1


def test_console_app_cli_args_w_config_no_config(tmp_path):
    cmdline = f"qp {tmp_path} --config"

    with mock.patch("repoze.sendmail.queue._log_error") as logged:
        app = queue_module.ConsoleApp(cmdline.split())

    assert app._error
    assert len(logged.call_args_list) == 1


def test_console_app_cli_args_w_bad_arg(tmp_path):
    cmdline = f"qp --foo {tmp_path}"

    with mock.patch("repoze.sendmail.queue._log_error") as logged:
        app = queue_module.ConsoleApp(cmdline.split())

    assert app._error
    assert len(logged.call_args_list) == 1


def test_console_app_cli_args_w_too_many_queues(tmp_path):
    cmdline = f"qp {tmp_path} foobar"

    with mock.patch("repoze.sendmail.queue._log_error") as logged:
        app = queue_module.ConsoleApp(cmdline.split())

    assert app._error
    assert len(logged.call_args_list) == 1


def test_console_app_ini_parse_bare(tmp_path):
    # Override nothing, make sure defaults come through
    bare_ini_path = tmp_path / "bare_qp.ini"
    bare_ini_path.write_text("[app:qp]\n\nqueue_path=foo\n")
    cmdline = f"qp --config {bare_ini_path} {tmp_path}"

    app = queue_module.ConsoleApp(cmdline.split())

    assert "qp" == app.script_name
    assert not app._error
    assert app.queue_path == str(tmp_path)
    assert app.hostname == "localhost"
    assert app.port == 25
    assert app.username is None
    assert app.password is None
    assert not app.force_tls
    assert not app.no_tls
    assert not app.debug_smtp


def test_console_app_ini_parse(tmp_path):
    # Override most everything
    ini_path = tmp_path / "qp.ini"
    ini_path.write_text(TEST_INI)
    cmdline = f"qp --config {ini_path}"

    app = queue_module.ConsoleApp(cmdline.split())

    assert app.script_name == "qp"
    assert not app._error
    assert app.queue_path == "hammer/dont/hurt/em"
    assert app.hostname == "testhost"
    assert app.port == 2525
    assert app.username == "Chris"
    assert app.password == "Rossi"
    assert not app.force_tls
    assert app.no_tls
    assert app.debug_smtp is True


def test_console_app__find_config_from_sys_executable(tmp_path):
    exe_path = tmp_path / "qp"
    etc_path = tmp_path / "etc"
    etc_path.mkdir()
    qp_ini_path = etc_path / "qp.ini"
    qp_ini_path.write_text(TEST_INI)
    cmdline = ["qp"]

    with mock.patch("sys.executable", str(exe_path)):
        app = queue_module.ConsoleApp(cmdline)

    assert app.script_name == "qp"
    assert not app._error
    assert app.queue_path == "hammer/dont/hurt/em"
    assert app.hostname == "testhost"
    assert app.port == 2525
    assert app.username == "Chris"
    assert app.password == "Rossi"
    assert not app.force_tls
    assert app.no_tls
    assert app.debug_smtp


def test_console_app_delivery(tmp_path):
    queue_dir = tmp_path / "queue"
    qmd = delivery_module.QueuedMailDelivery(queue_dir)
    maildir = maildir_module.Maildir(queue_dir, True)
    mailer = _makeMailerStub()
    from_addr = "foo@bar.foo"
    to_addr = "bar@foo.bar"
    message = email_message.Message()
    message["Subject"] = "Pants"
    message.set_payload("Nice pants, mister!")

    transaction.manager.begin()
    qmd.send(from_addr, to_addr, message)
    qmd.send(from_addr, to_addr, message)
    transaction.manager.commit()

    queued_messages = [m for m in maildir]
    assert 2 == len(queued_messages)
    assert 0 == len(mailer.sent_messages)

    cmdline = f"qp {queue_dir}"
    app = queue_module.ConsoleApp(cmdline.split())
    app.mailer = mailer
    app.main()

    queued_messages = [m for m in maildir]
    assert 0 == len(queued_messages)
    assert 2 == len(mailer.sent_messages)


TEST_INI = """\
[app:qp]
interval = 33
hostname = testhost
port = 2525
username = Chris
password = Rossi
force_tls = False
no_tls = True
queue_path = hammer/dont/hurt/em
debug_smtp = True
"""
