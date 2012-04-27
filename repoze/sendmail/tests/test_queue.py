import os.path
import shutil
import smtplib
import sys
from tempfile import mkdtemp
from unittest import TestCase

# BBB Python 2.5 & 3 compat
b = str
try:
    str = unicode
except NameError: # pragma: no cover
    import codecs
    def b(x): return codecs.latin_1_encode(x)[0]

try:
    from io import StringIO
    StringIO  # pyflakes
except ImportError: #pragma NO COVER
    from StringIO import StringIO  # BBB Python 2 vs 3 compat

from zope.interface import implementer

from repoze.sendmail import queue
from repoze.sendmail.interfaces import IMailer
from repoze.sendmail.queue import ConsoleApp

from repoze.sendmail.tests.test_delivery import _makeMailerStub
from repoze.sendmail.tests.test_delivery import MaildirStub

class LoggerStub(object):

    def __init__(self):
        self.infos = []
        self.errors = []

    def error(self, msg, *args, **kwargs):
        self.errors.append((msg, args, kwargs))

    def info(self, msg, *args, **kwargs):
        self.infos.append((msg, args, kwargs))


class BizzarreMailError(IOError):
    pass


class BrokenMailerStub(object):

    def __init__(self, *args, **kw):
        pass

    def send(self, fromaddr, toaddrs, message):
        raise BizzarreMailError("bad things happened while sending mail")

# BBB Python 2.5 compat
BrokenMailerStub = implementer(IMailer)(BrokenMailerStub)


class SMTPResponseExceptionMailerStub(object):

    def __init__(self, code):
        self.code = code

    def send(self, fromaddr, toaddrs, message):
        raise smtplib.SMTPResponseException(self.code,  'Serious Error')

# BBB Python 2.5 compat
SMTPResponseExceptionMailerStub = implementer(IMailer)(
    SMTPResponseExceptionMailerStub)


class TestQueueProcessor(TestCase):

    def setUp(self):
        from repoze.sendmail.queue import QueueProcessor
        self.qp = QueueProcessor(_makeMailerStub(), '/foo/bar/baz', MaildirStub)
        self.qp.log = LoggerStub()
        self.dir = mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_parseMessage(self):
        hdr = ('X-Actually-From: foo@example.com\n'
               'X-Actually-To: bar@example.com, baz@example.com\n')
        msg = ('Header: value\n'
               '\n'
               'Body\n')
        f, t, m = self.qp._parseMessage(StringIO(str(hdr + msg)))
        self.assertEquals(f, 'foo@example.com')
        self.assertEquals(t, ('bar@example.com', 'baz@example.com'))
        self.assertEquals(m.as_string(), msg)

    def test_delivery(self):
        self.filename = os.path.join(self.dir, 'message')
        temp = open(self.filename, "w+b")
        temp.write(b('X-Actually-From: foo@example.com\n')+
                   b('X-Actually-To: bar@example.com, baz@example.com\n')+
                   b('Header: value\n\nBody\n'))
        temp.close()
        self.qp.maildir.files.append(self.filename)
        self.qp.send_messages()
        
        sent_message = self.qp.mailer.sent_messages[0]
        self.assertEquals(sent_message[0], 'foo@example.com')
        self.assertEquals(sent_message[1], 
                          ('bar@example.com', 'baz@example.com'))
        self.assertEquals(sent_message[2].as_string(), 
                          'Header: value\n\nBody\n')
        self.assertFalse(os.path.exists(self.filename), 'File exists')
        self.assertEquals(self.qp.log.infos,
                          [('Mail from %s to %s sent.',
                            ('foo@example.com',
                             'bar@example.com, baz@example.com'),
                            {})])

    def test_error_logging(self):
        self.qp.mailer = BrokenMailerStub()
        self.filename = os.path.join(self.dir, 'message')
        temp = open(self.filename, "w+b")
        temp.write(b('X-Actually-From: foo@example.com\n')+
                   b('X-Actually-To: bar@example.com, baz@example.com\n')+
                   b('Header: value\n\nBody\n'))
        temp.close()
        self.qp.maildir.files.append(self.filename)
        self.qp.send_messages()
        self.assertEquals(self.qp.log.errors,
                          [('Error while sending mail from %s to %s.',
                            ('foo@example.com',
                             'bar@example.com, baz@example.com'),
                            {'exc_info': 1})])

    def test_error_logging_no_addrs(self):
        self.qp.mailer = BrokenMailerStub()
        self.filename = os.path.join(self.dir, 'message')
        temp = open(self.filename, "w+b")
        temp.write(b('Header: value\n\nBody\n'))
        temp.close()
        self.qp.maildir.files.append(self.filename)
        self.qp.send_messages()
        self.assertEquals(self.qp.log.errors,
                          [('Error while sending mail : %s ',
                            (self.filename,),
                            {'exc_info': True})])

    def test_smtp_response_error_transient(self):
        # Test a transient error
        self.qp.mailer = SMTPResponseExceptionMailerStub(451)
        self.filename = os.path.join(self.dir, 'message')
        temp = open(self.filename, "w+b")
        temp.write(b('X-Actually-From: foo@example.com\n')+
                   b('X-Actually-To: bar@example.com, baz@example.com\n')+
                   b('Header: value\n\nBody\n'))
        temp.close()
        self.qp.maildir.files.append(self.filename)
        self.qp.send_messages()

        # File must remail were it was, so it will be retried
        self.assertTrue(os.path.exists(self.filename))
        self.assertEquals(self.qp.log.errors,
                          [('Error while sending mail from %s to %s.',
                            ('foo@example.com',
                             'bar@example.com, baz@example.com'),
                            {'exc_info': 1})])

    def test_smtp_response_error_permanent(self):
        # Test a permanent error
        self.qp.mailer = SMTPResponseExceptionMailerStub(550)
        self.filename = os.path.join(self.dir, 'message')
        temp = open(self.filename, "w+b")
        temp.write(b('X-Actually-From: foo@example.com\n')+
                   b('X-Actually-To: bar@example.com, baz@example.com\n')+
                   b('Header: value\n\nBody\n'))
        temp.close()
        self.qp.maildir.files.append(self.filename)
        self.qp.send_messages()

        # File must be moved aside
        self.assertFalse(os.path.exists(self.filename))
        self.assertTrue(os.path.exists(os.path.join(self.dir,
                                                    '.rejected-message')))
        self.assertEqual(self.qp.log.errors,
                          [('Discarding email from %s to %s due to a '
                            'permanent error: %s',
                            ('foo@example.com',
                             'bar@example.com, baz@example.com',
                             (550, 'Serious Error')), {})])

    def test_concurrent_delivery(self):
        # Attempt to send message
        self.filename = os.path.join(self.dir, 'message')

        temp = open(self.filename, "w+b")
        temp.write(b('X-Actually-From: foo@example.com\n')+
                   b('X-Actually-To: bar@example.com, baz@example.com\n')+
                   b('Header: value\n\nBody\n'))
        temp.close()

        self.qp.maildir.files.append(self.filename)

        # Trick processor into thinking message is being delivered by
        # another process.
        head, tail = os.path.split(self.filename)
        tmp_filename = os.path.join(head, '.sending-' + tail)
        queue._os_link(self.filename, tmp_filename)
        try:
            self.qp.send_messages()

            self.assertEquals(self.qp.mailer.sent_messages, [])
            self.assertTrue(os.path.exists(self.filename),
                            'File does not exist')
            self.assertEquals(self.qp.log.infos, [])
        finally:
            os.unlink(tmp_filename)

    def test_concurrent_delivery_w_old_file(self):
        # Attempt to send message
        self.filename = os.path.join(self.dir, 'message')

        temp = open(self.filename, "w+b")
        temp.write(b('X-Actually-From: foo@example.com\n'
                     'X-Actually-To: bar@example.com, baz@example.com\n'
                     'Header: value\n\nBody\n'))
        temp.close()

        self.qp.maildir.files.append(self.filename)

        # Trick processor into thinking message is being delivered by
        # another process.
        head, tail = os.path.split(self.filename)
        tmp_filename = os.path.join(head, '.sending-' + tail)
        queue._os_link(self.filename, tmp_filename)
        os.utime(tmp_filename, (1,1)) #mtime/utime 1970-01-01T00:00:01Z
        self.qp.send_messages()

        sent_message = self.qp.mailer.sent_messages[0]
        self.assertEquals(sent_message[0], 'foo@example.com')
        self.assertEquals(sent_message[1], 
                          ('bar@example.com', 'baz@example.com'))
        self.assertEquals(sent_message[2].as_string(), 
                          'Header: value\n\nBody\n')
        self.assertFalse(os.path.exists(self.filename),
                         'File still exists')
        self.assertEquals(self.qp.log.infos,
                          [('Mail from %s to %s sent.',
                            ('foo@example.com',
                             'bar@example.com, baz@example.com'),
                            {})])
        self.assertFalse(os.path.exists(tmp_filename))

class TestConsoleApp(TestCase):
    def setUp(self):
        from repoze.sendmail.delivery import QueuedMailDelivery
        from repoze.sendmail.maildir import Maildir
        self.dir = mkdtemp()
        self.queue_dir = os.path.join(self.dir, "queue")
        self.delivery = QueuedMailDelivery(self.queue_dir)
        self.maildir = Maildir(self.queue_dir, True)
        self.mailer = _makeMailerStub()

        self.save_stderr = sys.stderr
        sys.stderr = self.stderr = StringIO()

    def tearDown(self):
        sys.stderr = self.save_stderr
        shutil.rmtree(self.dir)

    def _captureLoggedErrors(self, cmdline):
        from repoze.sendmail import queue
        logged = []
        monkey = _Monkey(queue, _log_error=logged.append)
        # py 25 compat, can't use with statement
        exc_info = ()
        try:
            monkey.__enter__()
            app = ConsoleApp(cmdline.split())
        except: # pragma: no cover
            exc_info = sys.exc_info()
        monkey.__exit__(*exc_info)
        return app, logged

    def test_args_simple_ok(self):
        # Simplest case that works
        cmdline = "qp %s" % self.dir
        app = ConsoleApp(cmdline.split())
        self.assertEquals("qp", app.script_name)
        self.assertFalse(app._error)
        self.assertEquals(self.dir, app.queue_path)
        self.assertEquals("localhost", app.hostname)
        self.assertEquals(25, app.port)
        self.assertEquals(None, app.username)
        self.assertEquals(None, app.password)
        self.assertFalse(app.force_tls)
        self.assertFalse(app.no_tls)
        self.assertFalse(app.debug_smtp)

    def test_args_simple_error(self):
        # Simplest case that doesn't work
        cmdline = "qp"
        app, logged = self._captureLoggedErrors(cmdline)
        self.assertEquals("qp", app.script_name)
        self.assertTrue(app._error)
        self.assertEquals(None, app.queue_path)
        self.assertEquals("localhost", app.hostname)
        self.assertEquals(25, app.port)
        self.assertEquals(None, app.username)
        self.assertEquals(None, app.password)
        self.assertFalse(app.force_tls)
        self.assertFalse(app.no_tls)
        self.assertFalse(app.debug_smtp)
        self.assertEqual(len(logged), 1)
        app.main()

    def test_args_full_monty(self):
        # Use (almost) all of the options
        cmdline = """qp --hostname foo --port 75
                        --username chris --password rossi --force-tls
                        --debug-smtp
                        %s""" % self.dir
        app = ConsoleApp(cmdline.split())
        self.assertEquals("qp", app.script_name)
        self.assertFalse(app._error)
        self.assertEquals(self.dir, app.queue_path)
        self.assertEquals("foo", app.hostname)
        self.assertEquals(75, app.port)
        self.assertEquals("chris", app.username)
        self.assertEquals("rossi", app.password)
        self.assertTrue(app.force_tls)
        self.assertFalse(app.no_tls)
        self.assertTrue(app.debug_smtp)

    def test_args_username_no_password(self):
        # Test username without password
        cmdline = "qp --username chris %s" % self.dir
        app, logged = self._captureLoggedErrors(cmdline)
        self.assertTrue(app._error)
        self.assertEqual(len(logged), 1)

    def test_args_force_tls_no_tls(self):
        # Test force_tls and no_tls
        cmdline = "qp --force-tls --no-tls %s" % self.dir
        app, logged = self._captureLoggedErrors(cmdline)
        self.assertTrue(app._error)
        self.assertEqual(len(logged), 1)

    def test_args_hostname_no_hostname(self):
        cmdline = 'qp %s --hostname' % self.dir
        app, logged = self._captureLoggedErrors(cmdline)
        self.assertTrue(app._error)
        self.assertEqual(len(logged), 1)

    def test_args_port_no_port(self):
        cmdline = 'qp %s --port' % self.dir
        app, logged = self._captureLoggedErrors(cmdline)
        self.assertTrue(app._error)
        self.assertEqual(len(logged), 1)

    def test_args_bad_port(self):
        cmdline = 'qp %s --port foo' % self.dir
        app, logged = self._captureLoggedErrors(cmdline)
        self.assertTrue(app._error)
        self.assertEqual(len(logged), 1)

    def test_args_username_no_username(self):
        cmdline = 'qp %s --username' % self.dir
        app, logged = self._captureLoggedErrors(cmdline)
        self.assertTrue(app._error)
        self.assertEqual(len(logged), 1)

    def test_args_password_no_password(self):
        cmdline = 'qp %s --password' % self.dir
        app, logged = self._captureLoggedErrors(cmdline)
        self.assertTrue(app._error)
        self.assertEqual(len(logged), 1)

    def test_args_config_no_config(self):
        cmdline = 'qp %s --config' % self.dir
        app, logged = self._captureLoggedErrors(cmdline)
        self.assertTrue(app._error)
        self.assertEqual(len(logged), 1)

    def test_args_bad_arg(self):
        cmdline = 'qp --foo %s' % self.dir
        app, logged = self._captureLoggedErrors(cmdline)
        self.assertTrue(app._error)
        self.assertEqual(len(logged), 1)

    def test_args_too_many_queues(self):
        cmdline = 'qp %s foobar' % self.dir
        app, logged = self._captureLoggedErrors(cmdline)
        self.assertTrue(app._error)
        self.assertEqual(len(logged), 1)

    def test_ini_parse(self):
        ini_path = os.path.join(self.dir, "qp.ini")
        f = open(ini_path, "w")
        f.write(test_ini)
        f.close()

        # Override most everything
        cmdline = """qp --config %s""" % ini_path
        app = ConsoleApp(cmdline.split())
        self.assertEquals("qp", app.script_name)
        self.assertFalse(app._error)
        self.assertEquals("hammer/dont/hurt/em", app.queue_path)
        self.assertEquals("testhost", app.hostname)
        self.assertEquals(2525, app.port)
        self.assertEquals("Chris", app.username)
        self.assertEquals("Rossi", app.password)
        self.assertFalse(app.force_tls)
        self.assertTrue(app.no_tls)

        # Override nothing, make sure defaults come through
        f = open(ini_path, "w")
        f.write("[app:qp]\n\nqueue_path=foo\n")
        f.close()

        cmdline = """qp --config %s %s""" % (ini_path, self.dir)
        app = ConsoleApp(cmdline.split())
        self.assertEquals("qp", app.script_name)
        self.assertFalse(app._error)
        self.assertEquals(self.dir, app.queue_path)
        self.assertEquals("localhost", app.hostname)
        self.assertEquals(25, app.port)
        self.assertEquals(None, app.username)
        self.assertEquals(None, app.password)
        self.assertFalse(app.force_tls)
        self.assertFalse(app.no_tls)

    def test_delivery(self):
        from email.message import Message
        from_addr = "foo@bar.foo"
        to_addr = "bar@foo.bar"
        message = Message()
        message['Subject'] = 'Pants'
        message.set_payload('Nice pants, mister!')

        import transaction
        transaction.manager.begin()
        self.delivery.send(from_addr, to_addr, message)
        self.delivery.send(from_addr, to_addr, message)
        transaction.manager.commit()

        queued_messages = [m for m in self.maildir]
        self.assertEqual(2, len(queued_messages))
        self.assertEqual(0, len(self.mailer.sent_messages))

        cmdline = "qp %s" % self.queue_dir
        app = ConsoleApp(cmdline.split())
        app.mailer = self.mailer
        app.main()

        queued_messages = [m for m in self.maildir]
        self.assertEqual(0, len(queued_messages))
        self.assertEqual(2, len(self.mailer.sent_messages))

test_ini = """[app:qp]
interval = 33
hostname = testhost
port = 2525
username = Chris
password = Rossi
force_tls = False
no_tls = True
queue_path = hammer/dont/hurt/em
"""


class _Monkey(object):

    def __init__(self, module, **replacements):
        self.module = module
        self.orig = {}
        self.replacements = replacements
        
    def __enter__(self):
        for k, v in self.replacements.items():
            orig = getattr(self.module, k, self)
            if orig is not self:
                self.orig[k] = orig
            setattr(self.module, k, v)

    def __exit__(self, *exc_info):
        for k, v in self.replacements.items():
            if k in self.orig:
                setattr(self.module, k, self.orig[k])
            else: #pragma NO COVERSGE
                delattr(self.module, k)
