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


class TestMailDataManager(unittest.TestCase):

    def _getTargetClass(self):
        from repoze.sendmail.delivery import MailDataManager
        return MailDataManager

    def _makeOne(self, callable=object, args=(), onAbort=None):
        return self._getTargetClass()(callable, args, onAbort)

    def test_class_conforms_to_IDataManager(self):
        from transaction.interfaces import IDataManager
        from zope.interface.verify import verifyClass
        verifyClass(IDataManager, self._getTargetClass())

    def test_instance_conforms_to_IDataManager(self):
        from transaction.interfaces import IDataManager
        from zope.interface.verify import verifyObject
        verifyObject(IDataManager, self._makeOne())

    def test_ctor(self):
        manager = self._makeOne(object, (1, 2))
        self.assertEqual(manager.callable, object)
        self.assertEqual(manager.args, (1, 2))

    def test_sortKey(self):
        manager = self._makeOne()
        self.assertEqual(manager.sortKey(), str(id(manager)))


class TestDirectMailDelivery(unittest.TestCase):

    def _getTargetClass(self):
        from repoze.sendmail.delivery import DirectMailDelivery
        return DirectMailDelivery

    def _makeOne(self, mailer=None):
        return self._getTargetClass()(mailer)

    def test_class_conforms_to_IMailDelivery(self):
        from zope.interface.verify import verifyClass
        from repoze.sendmail.interfaces import IMailDelivery
        verifyClass(IMailDelivery, self._getTargetClass())

    def test_instance_conforms_to_IMailDelivery(self):
        from zope.interface.verify import verifyObject
        from repoze.sendmail.interfaces import IMailDelivery
        verifyObject(IMailDelivery, self._makeOne())

    def test_ctor(self):
        mailer = _makeMailerStub()
        delivery = self._makeOne(mailer)
        self.assertEqual(delivery.mailer, mailer)

    def test_send(self):
        from repoze.sendmail.delivery import DirectMailDelivery
        import transaction
        from email.message import Message
        mailer = _makeMailerStub()
        delivery = DirectMailDelivery(mailer)
        fromaddr = 'Jim <jim@example.com'
        toaddrs = ('Guido <guido@example.com>',
                   'Steve <steve@examplecom>')
        message = Message()
        message['From'] = 'Jim <jim@example.org>'
        message['To'] = 'some-zope-coders:;'
        message['Date'] = 'Date: Mon, 19 May 2003 10:17:36 -0400'
        message['Message-Id'] = ext_msgid = '<20030519.1234@example.org>'
        message['Subject'] = 'example'
        message.set_payload('This is just an example\n')

        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assertEqual(msgid, '<20030519.1234@example.org>')
        self.assertEqual(mailer.sent_messages, [])
        transaction.commit()
        self.assertEqual(mailer.sent_messages,
                          [(fromaddr, toaddrs, message)])

        mailer.sent_messages = []
        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assertTrue('@' in msgid)
        self.assertEqual(mailer.sent_messages, [])
        transaction.commit()
        self.assertEqual(len(mailer.sent_messages), 1)
        self.assertEqual(mailer.sent_messages[0][0], fromaddr)
        self.assertEqual(mailer.sent_messages[0][1], toaddrs)
        self.assertEqual(mailer.sent_messages[0][2].get_payload(),
                          'This is just an example\n')
        self.assertEqual(message['Message-Id'],  msgid)
        self.assertEqual(message['Message-Id'], ext_msgid)

        mailer.sent_messages = []
        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assertEqual(mailer.sent_messages, [])
        transaction.abort()
        self.assertEqual(mailer.sent_messages, [])

    def test_send_returns_messageId(self):
        from repoze.sendmail.delivery import DirectMailDelivery
        from email.message import Message
        mailer = _makeMailerStub()
        delivery = DirectMailDelivery(mailer)
        fromaddr = 'Jim <jim@example.com'
        toaddrs = ('Guido <guido@example.com>',
                   'Steve <steve@examplecom>')
        message = Message()
        message['From'] = 'Jim <jim@example.org>'
        message['To'] = 'some-zope-coders:;'
        message['Date'] = 'Date: Mon, 19 May 2003 10:17:36 -0400'
        message['Subject'] = 'example'
        message.set_payload('This is just an example\n')

        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assertTrue('.repoze.sendmail@' in msgid)
        self.assertEqual(message['Message-Id'],  msgid)


class TestQueuedMailDelivery(unittest.TestCase):

    def setUp(self):
        import repoze.sendmail.delivery as mail_delivery_module
        self.mail_delivery_module = mail_delivery_module
        self.old_Maildir = mail_delivery_module.Maildir
        mail_delivery_module.Maildir = MaildirStub

    def tearDown(self):
        self.mail_delivery_module.Maildir = self.old_Maildir
        MaildirMessageStub.commited_messages = []
        MaildirMessageStub.aborted_messages = []

    def _getTargetClass(self):
        from repoze.sendmail.delivery import QueuedMailDelivery
        return QueuedMailDelivery

    def _makeOne(self, queuePath='/tmp'):
        return self._getTargetClass()(queuePath)

    def _makeMessage(self):
        from email.message import Message
        message = Message()
        message['From'] = 'Jim <jim@example.org>'
        message['To'] = 'some-zope-coders:;'
        message['Date'] = 'Date: Mon, 19 May 2003 10:17:36 -0400'
        message['Message-Id'] = '<20030519.1234@example.org>'

        message.set_payload('This is just an example\n')
        return message

    def test_class_conforms_to_IMailDelivery(self):
        from zope.interface.verify import verifyClass
        from repoze.sendmail.interfaces import IMailDelivery
        verifyClass(IMailDelivery, self._getTargetClass())

    def test_instance_conforms_to_IMailDelivery(self):
        from zope.interface.verify import verifyObject
        from repoze.sendmail.interfaces import IMailDelivery
        verifyObject(IMailDelivery, self._makeOne())

    def test_ctor(self):
        delivery = self._makeOne('/path/to/mailbox')
        self.assertEqual(delivery.queuePath, '/path/to/mailbox')

    def test_send(self):
        import transaction
        from repoze.sendmail.delivery import QueuedMailDelivery
        from repoze.sendmail._compat import text_type
        delivery = QueuedMailDelivery('/path/to/mailbox')
        fromaddr = 'jim@example.com'
        toaddrs = ('guido@example.com',
                   'steve@example.com')

        message = self._makeMessage()
        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assertEqual(msgid, '<20030519.1234@example.org>')
        self.assertEqual(MaildirMessageStub.commited_messages, [])
        self.assertEqual(MaildirMessageStub.aborted_messages, [])
        transaction.commit()
        self.assertEqual(len(MaildirMessageStub.commited_messages), 1)
        self.assertEqual(MaildirMessageStub.aborted_messages, [])
        message = MaildirMessageStub.commited_messages[0]
        self.assertEqual(text_type(message['X-Actually-From']), fromaddr)
        self.assertEqual(text_type(
            message['X-Actually-To']), ','.join(toaddrs))

        MaildirMessageStub.commited_messages = []
        message = self._makeMessage()
        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assertTrue('@' in msgid)
        self.assertEqual(MaildirMessageStub.commited_messages, [])
        self.assertEqual(MaildirMessageStub.aborted_messages, [])
        transaction.commit()
        self.assertEqual(len(MaildirMessageStub.commited_messages), 1)
        self.assertEqual(MaildirMessageStub.commited_messages[0].get_payload(),
                         'This is just an example\n')
        self.assertEqual(message['Message-Id'], msgid)
        self.assertEqual(message['Message-Id'], '<20030519.1234@example.org>')
        self.assertEqual(MaildirMessageStub.aborted_messages, [])

        MaildirMessageStub.commited_messages = []
        message = self._makeMessage()
        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assertEqual(MaildirMessageStub.commited_messages, [])
        self.assertEqual(MaildirMessageStub.aborted_messages, [])
        transaction.abort()
        self.assertEqual(MaildirMessageStub.commited_messages, [])
        self.assertEqual(len(MaildirMessageStub.aborted_messages), 1)


class TestQueuedMailDeliveryWithMaildir(unittest.TestCase):

    def setUp(self):
        import os
        import tempfile
        from repoze.sendmail.queue import QueueProcessor
        self.dir = tempfile.mkdtemp()
        self.maildir_path = os.path.join(self.dir, 'Maildir')
        self.qp = QueueProcessor(_makeMailerStub(), self.maildir_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir)

    def _getTargetClass(self):
        from repoze.sendmail.delivery import QueuedMailDelivery
        return QueuedMailDelivery

    def _makeOne(self, queuePath='/tmp'):
        return self._getTargetClass()(queuePath)

    def test_send_w_non_ASCII_addrs(self):
        import os
        from email.mime import base
        import transaction
        from repoze.sendmail._compat import b
        delivery = self._makeOne(self.maildir_path)

        non_ascii = b('LaPe\xc3\xb1a').decode('utf-8')
        fromaddr = non_ascii+' <jim@example.com>'
        toaddrs = (non_ascii+' <guido@recip.com>',)
        message = base.MIMEBase('text', 'plain')
        message['From'] = fromaddr
        message['To'] = ','.join(toaddrs)

        delivery.send(fromaddr, toaddrs, message)
        self.assertTrue(os.listdir(os.path.join(self.maildir_path, 'tmp')))
        self.assertFalse(os.listdir(os.path.join(self.maildir_path, 'new')))
        transaction.commit()
        self.assertFalse(os.listdir(os.path.join(self.maildir_path, 'tmp')))
        self.assertTrue(os.listdir(os.path.join(self.maildir_path, 'new')))

        self.qp.send_messages()
        self.assertTrue(len(self.qp.mailer.sent_messages), 1)
        queued_fromaddr, queued_toaddrs, queued_message = (
            self.qp.mailer.sent_messages[0])
        self.assertEqual(queued_fromaddr, fromaddr)
        self.assertEqual(queued_toaddrs, toaddrs)


class TestSendmailDelivery(unittest.TestCase):

    def _getTargetClass(self):
        from repoze.sendmail.delivery import SendmailDelivery
        return SendmailDelivery

    def _makeOne(self, mailer=None):
        return self._getTargetClass()(mailer)

    def test_class_conforms_to_IMailDelivery(self):
        from zope.interface.verify import verifyClass
        from repoze.sendmail.interfaces import IMailDelivery
        verifyClass(IMailDelivery, self._getTargetClass())

    def test_instance_conforms_to_IMailDelivery(self):
        from zope.interface.verify import verifyObject
        from repoze.sendmail.interfaces import IMailDelivery
        verifyObject(IMailDelivery, self._makeOne())

    def test_ctor(self):
        mailer = _makeMailerStub()
        delivery = self._makeOne(mailer)
        self.assertEqual(delivery.mailer, mailer)

    def test_send(self):
        from repoze.sendmail.delivery import SendmailDelivery
        import transaction
        from email.message import Message
        mailer = _makeMailerStub()
        delivery = SendmailDelivery(mailer)
        fromaddr = 'Jim <jim@example.com'
        toaddrs = ('Guido <guido@example.com>',
                   'Steve <steve@examplecom>')
        message = Message()
        message['From'] = 'Jim <jim@example.org>'
        message['To'] = 'some-zope-coders:;'
        message['Date'] = 'Date: Mon, 19 May 2003 10:17:36 -0400'
        message['Message-Id'] = ext_msgid = '<20030519.1234@example.org>'
        message['Subject'] = 'example'
        message.set_payload('This is just an example\n')

        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assertEqual(msgid, '<20030519.1234@example.org>')
        self.assertEqual(mailer.sent_messages, [])
        transaction.commit()
        self.assertEqual(mailer.sent_messages,
                          [(fromaddr, toaddrs, message)])

        mailer.sent_messages = []
        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assertTrue('@' in msgid)
        self.assertEqual(mailer.sent_messages, [])
        transaction.commit()
        self.assertEqual(len(mailer.sent_messages), 1)
        self.assertEqual(mailer.sent_messages[0][0], fromaddr)
        self.assertEqual(mailer.sent_messages[0][1], toaddrs)
        self.assertEqual(mailer.sent_messages[0][2].get_payload(),
                          'This is just an example\n')
        self.assertEqual(message['Message-Id'],  msgid)
        self.assertEqual(message['Message-Id'], ext_msgid)

        mailer.sent_messages = []
        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assertEqual(mailer.sent_messages, [])
        transaction.abort()
        self.assertEqual(mailer.sent_messages, [])

    def test_send_returns_messageId(self):
        from repoze.sendmail.delivery import SendmailDelivery
        from email.message import Message
        mailer = _makeMailerStub()
        delivery = SendmailDelivery(mailer)
        fromaddr = 'Jim <jim@example.com'
        toaddrs = ('Guido <guido@example.com>',
                   'Steve <steve@examplecom>')
        message = Message()
        message['From'] = 'Jim <jim@example.org>'
        message['To'] = 'some-zope-coders:;'
        message['Date'] = 'Date: Mon, 19 May 2003 10:17:36 -0400'
        message['Subject'] = 'example'
        message.set_payload('This is just an example\n')

        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assertTrue('.repoze.sendmail@' in msgid)
        self.assertEqual(message['Message-Id'],  msgid)


class MaildirMessageStub(object):
    message = None
    commited_messages = []  # this list is shared among all instances
    aborted_messages = []   # this one too
    _closed = False

    def __init__(self, message):
        self.message = message

    def commit(self):
        self._commited = True
        self.commited_messages.append(self.message)

    def abort(self):
        self._aborted = True
        self.aborted_messages.append(self.message)


class MaildirStub(object):

    def __init__(self, path, create=False):
        self.path = path
        self.create = create
        self.msgs = []
        self.files = []

    def __iter__(self):
        return iter(self.files)

    def add(self, message):
        m = MaildirMessageStub(message)
        self.msgs.append(m)
        return m

def _makeMailerStub(*args, **kw):
    from zope.interface import implementer
    from repoze.sendmail.interfaces import IMailer
    implementer(IMailer)
    class MailerStub(object):
        def __init__(self, *args, **kw):
            self.sent_messages = []
        def send(self, fromaddr, toaddrs, message):
            self.sent_messages.append((fromaddr, toaddrs, message))
    return MailerStub(*args, **kw)
