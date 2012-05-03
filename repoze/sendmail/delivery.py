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
"""
Mail Delivery utility implementation

This module contains various implementations of Mail Deliveries.
"""

from email.message import Message
from email.header import Header
from email.parser import Parser
from email.utils import formatdate
from email.utils import make_msgid

from zope.interface import implementer
from repoze.sendmail.interfaces import IMailDelivery
from repoze.sendmail.maildir import Maildir
from repoze.sendmail import encoding
from transaction.interfaces import IDataManager
import transaction

class MailDataManager(object):

    def __init__(self, callable, args=(), onAbort=None):
        self.callable = callable
        self.args = args
        self.onAbort = onAbort
        # Use the default thread transaction manager.
        self.transaction_manager = transaction.manager

    def commit(self, transaction):
        pass

    def abort(self, transaction):
        if self.onAbort:
            self.onAbort()

    def sortKey(self):
        return id(self)

    # No subtransaction support.
    def abort_sub(self, transaction):
        pass  #pragma NO COVERAGE

    commit_sub = abort_sub

    def beforeCompletion(self, transaction):
        pass  #pragma NO COVERAGE

    afterCompletion = beforeCompletion

    def tpc_begin(self, transaction, subtransaction=False):
        assert not subtransaction

    def tpc_vote(self, transaction):
        pass

    def tpc_finish(self, transaction):
        self.callable(*self.args)

    tpc_abort = abort

# BBB Python 2.5 compat
MailDataManager = implementer(IDataManager)(MailDataManager)


class AbstractMailDelivery(object):

    def send(self, fromaddr, toaddrs, message):
        assert isinstance(message, Message), \
               'Message must be instance of email.message.Message'
        encoding.cleanup_message(message)
        messageid = message['Message-Id']
        if messageid is None:
            messageid = message['Message-Id'] = make_msgid('repoze.sendmail')
        if message['Date'] is None:
            message['Date'] = formatdate()
        transaction.get().join(
            self.createDataManager(fromaddr, toaddrs, message))
        return messageid


class DirectMailDelivery(AbstractMailDelivery):

    def __init__(self, mailer):
        self.mailer = mailer

    def createDataManager(self, fromaddr, toaddrs, message):
        return MailDataManager(self.mailer.send,
                               args=(fromaddr, toaddrs, message))

# BBB Python 2.5 compat
DirectMailDelivery = implementer(IMailDelivery)(DirectMailDelivery)


class QueuedMailDelivery(AbstractMailDelivery):

    def __init__(self, queuePath):
        self._queuePath = queuePath

    queuePath = property(lambda self: self._queuePath)
    processor_thread = None

    def createDataManager(self, fromaddr, toaddrs, message):
        message = copy_message(message)
        message['X-Actually-From'] = Header(fromaddr, 'utf-8')
        message['X-Actually-To'] = Header(','.join(toaddrs), 'utf-8')
        maildir = Maildir(self.queuePath, True)
        tx_message = maildir.add(message)
        return MailDataManager(tx_message.commit, onAbort=tx_message.abort)

# BBB Python 2.5 compat
QueuedMailDelivery = implementer(IMailDelivery)(QueuedMailDelivery)


def copy_message(message):
    parser = Parser()
    return parser.parsestr(message.as_string())
