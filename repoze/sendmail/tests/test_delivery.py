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
from unittest import TestCase, TestSuite, makeSuite

import transaction
from zope.interface import implements
from zope.interface.verify import verifyObject

from repoze.sendmail.interfaces import IMailer


class MailerStub(object):

    implements(IMailer)
    def __init__(self, *args, **kw):
        self.sent_messages = []

    def send(self, fromaddr, toaddrs, message):
        self.sent_messages.append((fromaddr, toaddrs, message))


class TestMailDataManager(TestCase):

    def testInterface(self):
        from transaction.interfaces import IDataManager
        from repoze.sendmail.delivery import MailDataManager
        manager = MailDataManager(object, (1, 2))
        verifyObject(IDataManager, manager)
        self.assertEqual(manager.callable, object)
        self.assertEqual(manager.args, (1, 2))

class TestDirectMailDelivery(TestCase):

    def testInterface(self):
        from repoze.sendmail.interfaces import IMailDelivery
        from repoze.sendmail.delivery import DirectMailDelivery
        mailer = MailerStub()
        delivery = DirectMailDelivery(mailer)
        verifyObject(IMailDelivery, delivery)
        self.assertEqual(delivery.mailer, mailer)

    def testSend(self):
        from repoze.sendmail.delivery import DirectMailDelivery
        from email.message import Message
        mailer = MailerStub()
        delivery = DirectMailDelivery(mailer)
        fromaddr = 'Jim <jim@example.com'
        toaddrs = ('Guido <guido@example.com>',
                   'Steve <steve@examplecom>')
        message = Message()
        message['From'] = 'Jim <jim@example.org>'
        message['To'] = 'some-zope-coders:;'
        message['Date'] = 'Date: Mon, 19 May 2003 10:17:36 -0400'
        message['Message-Id'] = '<20030519.1234@example.org>'
        message['Subject'] = 'example'
        message.set_payload('This is just an example\n')

        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assertEquals(msgid, '<20030519.1234@example.org>')
        self.assertEquals(mailer.sent_messages, [])
        transaction.commit()
        self.assertEquals(mailer.sent_messages,
                          [(fromaddr, toaddrs, message)])

        mailer.sent_messages = []
        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assert_('@' in msgid)
        self.assertEquals(mailer.sent_messages, [])
        transaction.commit()
        self.assertEquals(len(mailer.sent_messages), 1)
        self.assertEquals(mailer.sent_messages[0][0], fromaddr)
        self.assertEquals(mailer.sent_messages[0][1], toaddrs)
        self.assertEquals(mailer.sent_messages[0][2].get_payload(),
                          'This is just an example\n')
        self.assertEqual(message['Message-Id'],  msgid)

        mailer.sent_messages = []
        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assertEquals(mailer.sent_messages, [])
        transaction.abort()
        self.assertEquals(mailer.sent_messages, [])


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


class TestQueuedMailDelivery(TestCase):

    def setUp(self):
        import repoze.sendmail.delivery as mail_delivery_module
        self.mail_delivery_module = mail_delivery_module
        self.old_Maildir = mail_delivery_module.Maildir
        mail_delivery_module.Maildir = MaildirStub

    def tearDown(self):
        self.mail_delivery_module.Maildir = self.old_Maildir
        MaildirMessageStub.commited_messages = []
        MaildirMessageStub.aborted_messages = []

    def testInterface(self):
        from repoze.sendmail.interfaces import IMailDelivery
        from repoze.sendmail.delivery import QueuedMailDelivery
        delivery = QueuedMailDelivery('/path/to/mailbox')
        verifyObject(IMailDelivery, delivery)
        self.assertEqual(delivery.queuePath, '/path/to/mailbox')

    def testSend(self):
        from email.message import Message
        from repoze.sendmail.delivery import QueuedMailDelivery
        delivery = QueuedMailDelivery('/path/to/mailbox')
        fromaddr = 'jim@example.com'
        toaddrs = ('guido@example.com',
                   'steve@example.com')
        message = Message()
        message['From'] = 'Jim <jim@example.org>'
        message['To'] = 'some-zope-coders:;'
        message['Date'] = 'Date: Mon, 19 May 2003 10:17:36 -0400'
        message['Message-Id'] = '<20030519.1234@example.org>'
        message['Subject'] = 'example'
        message.set_payload('This is just an example\n')

        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assertEquals(msgid, '<20030519.1234@example.org>')
        self.assertEquals(MaildirMessageStub.commited_messages, [])
        self.assertEquals(MaildirMessageStub.aborted_messages, [])
        transaction.commit()
        self.assertEquals(len(MaildirMessageStub.commited_messages), 1)
        self.assertEquals(MaildirMessageStub.aborted_messages, [])
        message = MaildirMessageStub.commited_messages[0]
        self.assertEqual(message['X-Actually-From'], fromaddr)
        self.assertEqual(message['X-Actually-To'], ','.join(toaddrs))

        MaildirMessageStub.commited_messages = []
        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assert_('@' in msgid)
        self.assertEquals(MaildirMessageStub.commited_messages, [])
        self.assertEquals(MaildirMessageStub.aborted_messages, [])
        transaction.commit()
        self.assertEquals(len(MaildirMessageStub.commited_messages), 1)
        self.assertEqual(MaildirMessageStub.commited_messages[0].get_payload(),
                         'This is just an example\n')
        self.assertEqual(message['Message-Id'], msgid)
        self.assertEquals(MaildirMessageStub.aborted_messages, [])

        MaildirMessageStub.commited_messages = []
        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assertEquals(MaildirMessageStub.commited_messages, [])
        self.assertEquals(MaildirMessageStub.aborted_messages, [])
        transaction.abort()
        self.assertEquals(MaildirMessageStub.commited_messages, [])
        self.assertEquals(len(MaildirMessageStub.aborted_messages), 1)
