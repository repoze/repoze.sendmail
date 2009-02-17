import os.path
import shutil
import smtplib
from tempfile import mkdtemp
import unittest
from unittest import TestCase, TestSuite, makeSuite

from zope.interface import implements

from repoze.sendmail import queue
from repoze.sendmail.interfaces import IMailer
from repoze.sendmail.queue import ConsoleApp

from repoze.sendmail.tests.test_delivery import MailerStub
from repoze.sendmail.tests.test_delivery import MaildirStub

class LoggerStub(object):

    def __init__(self):
        self.infos = []
        self.errors = []

    def getLogger(name):
        return self

    def error(self, msg, *args, **kwargs):
        self.errors.append((msg, args, kwargs))

    def info(self, msg, *args, **kwargs):
        self.infos.append((msg, args, kwargs))


class BizzarreMailError(IOError):
    pass


class BrokenMailerStub(object):

    implements(IMailer)
    def __init__(self, *args, **kw):
        pass

    def send(self, fromaddr, toaddrs, message):
        raise BizzarreMailError("bad things happened while sending mail")


class SMTPResponseExceptionMailerStub(object):

    implements(IMailer)
    def __init__(self, code):
        self.code = code

    def send(self, fromaddr, toaddrs, message):
        raise smtplib.SMTPResponseException(self.code,  'Serious Error')

class TestQueueProcessor(TestCase):

    def setUp(self):
        from repoze.sendmail.queue import QueueProcessor
        self.qp = QueueProcessor()
        self.qp.maildir = MaildirStub('/foo/bar/baz')
        self.qp.mailer = MailerStub()
        self.qp.log = LoggerStub()
        self.dir = mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_parseMessage(self):
        hdr = ('X-Zope-From: foo@example.com\n'
               'X-Zope-To: bar@example.com, baz@example.com\n')
        msg = ('Header: value\n'
               '\n'
               'Body\n')
        f, t, m = self.qp._parseMessage(hdr + msg)
        self.assertEquals(f, 'foo@example.com')
        self.assertEquals(t, ('bar@example.com', 'baz@example.com'))
        self.assertEquals(m, msg)

    def test_delivery(self):
        self.filename = os.path.join(self.dir, 'message')
        temp = open(self.filename, "w+b")
        temp.write('X-Zope-From: foo@example.com\n'
                   'X-Zope-To: bar@example.com, baz@example.com\n'
                   'Header: value\n\nBody\n')
        temp.close()
        self.qp.maildir.files.append(self.filename)
        self.qp.send_messages()
        self.assertEquals(self.qp.mailer.sent_messages,
                          [('foo@example.com',
                            ('bar@example.com', 'baz@example.com'),
                            'Header: value\n\nBody\n')])
        self.failIf(os.path.exists(self.filename), 'File exists')
        self.assertEquals(self.qp.log.infos,
                          [('Mail from %s to %s sent.',
                            ('foo@example.com',
                             'bar@example.com, baz@example.com'),
                            {})])

    def test_error_logging(self):
        self.qp.mailer = BrokenMailerStub()
        self.filename = os.path.join(self.dir, 'message')
        temp = open(self.filename, "w+b")
        temp.write('X-Zope-From: foo@example.com\n'
                   'X-Zope-To: bar@example.com, baz@example.com\n'
                   'Header: value\n\nBody\n')
        temp.close()
        self.qp.maildir.files.append(self.filename)
        self.qp.send_messages()
        self.assertEquals(self.qp.log.errors,
                          [('Error while sending mail from %s to %s.',
                            ('foo@example.com',
                             'bar@example.com, baz@example.com'),
                            {'exc_info': 1})])

    def test_smtp_response_error_transient(self):
        # Test a transient error
        self.qp.mailer = SMTPResponseExceptionMailerStub(451)
        self.filename = os.path.join(self.dir, 'message')
        temp = open(self.filename, "w+b")
        temp.write('X-Zope-From: foo@example.com\n'
                   'X-Zope-To: bar@example.com, baz@example.com\n'
                   'Header: value\n\nBody\n')
        temp.close()
        self.qp.maildir.files.append(self.filename)
        self.qp.send_messages()

        # File must remail were it was, so it will be retried
        self.failUnless(os.path.exists(self.filename))
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
        temp.write('X-Zope-From: foo@example.com\n'
                   'X-Zope-To: bar@example.com, baz@example.com\n'
                   'Header: value\n\nBody\n')
        temp.close()
        self.qp.maildir.files.append(self.filename)
        self.qp.send_messages()
        
        # File must be moved aside
        self.failIf(os.path.exists(self.filename))
        self.failUnless(os.path.exists(os.path.join(self.dir,
                                                    '.rejected-message')))
        self.assertEquals(self.qp.log.errors,
                          [('Discarding email from %s to %s due to a '
                            'permanent error: %s',
                            ('foo@example.com',
                             'bar@example.com, baz@example.com',
                             "(550, 'Serious Error')"), {})])


    def test_concurrent_delivery(self):
        # Attempt to send message
        self.filename = os.path.join(self.dir, 'message')

        temp = open(self.filename, "w+b")
        temp.write('X-Zope-From: foo@example.com\n'
                   'X-Zope-To: bar@example.com, baz@example.com\n'
                   'Header: value\n\nBody\n')
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
            self.failUnless(os.path.exists(self.filename), 
                            'File does not exist')
            self.assertEquals(self.qp.log.infos, [])
        finally:
            os.unlink(tmp_filename)
            
class TestConsoleApp(TestCase):
    def setUp(self):
        self.dir = mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_args_processing(self):
        # Simplest case that works
        cmdline = "qp %s" % self.dir
        app = ConsoleApp(cmdline.split())
        self.assertEquals("qp", app.script_name)
        self.assertFalse(app._error)
        self.assertEquals(self.dir, app.queue_path)
        self.assertFalse(app.daemon)
        self.assertEquals(3, app.interval)
        self.assertEquals("localhost", app.hostname)
        self.assertEquals(25, app.port)
        self.assertEquals(None, app.username)
        self.assertEquals(None, app.password)
        self.assertFalse(app.force_tls)
        self.assertFalse(app.no_tls)
        
        # Simplest case that doesn't work
        cmdline = "qp"
        app = ConsoleApp(cmdline.split())
        self.assertEquals("qp", app.script_name)
        self.assertTrue(app._error)
        self.assertEquals(None, app.queue_path)
        self.assertFalse(app.daemon)
        self.assertEquals(3, app.interval)
        self.assertEquals("localhost", app.hostname)
        self.assertEquals(25, app.port)
        self.assertEquals(None, app.username)
        self.assertEquals(None, app.password)
        self.assertFalse(app.force_tls)
        self.assertFalse(app.no_tls)
              
        # Use (almost) all of the options
        cmdline = """qp --daemon --interval 7 --hostname foo --port 75 
                        --username chris --password rossi --force-tls 
                        %s""" % self.dir
        app = ConsoleApp(cmdline.split())
        self.assertEquals("qp", app.script_name)
        self.assertFalse(app._error)
        self.assertEquals(self.dir, app.queue_path)
        self.assertTrue(app.daemon)
        self.assertEquals(7, app.interval)
        self.assertEquals("foo", app.hostname)
        self.assertEquals(75, app.port)
        self.assertEquals("chris", app.username)
        self.assertEquals("rossi", app.password)
        self.assertTrue(app.force_tls)
        self.assertFalse(app.no_tls)
        
        # Test username without password
        cmdline = "qp --username chris %s" % self.dir
        app = ConsoleApp(cmdline.split())
        self.assertTrue(app._error)
        
        # Test force_tls and no_tls
        comdline = "qp --force-tls --no-tls %s" % self.dir
        self.assertTrue(app._error)
        
        
def test_suite():
    return TestSuite((
        makeSuite(TestQueueProcessor),
        makeSuite(TestConsoleApp),
        ))

if __name__ == '__main__':
    unittest.main()
