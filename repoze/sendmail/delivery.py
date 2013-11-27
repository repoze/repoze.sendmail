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
import logging

from zope.interface import implementer
from repoze.sendmail.interfaces import IMailDelivery
from repoze.sendmail.maildir import Maildir
from repoze.sendmail import encoding
import transaction
from transaction.interfaces import ISavepointDataManager
from transaction.interfaces import IDataManagerSavepoint

log = logging.getLogger(__name__)

#
# DEBUG_FLOW is useful when mapping out the interactions with `transaction`
# It just prints out the current function name / state
#
DEBUG_FLOW = False
if DEBUG_FLOW: #pragma NO COVER
    import sys
    log.setLevel(logging.DEBUG)
    h1 = logging.StreamHandler(sys.stdout)
    log.addHandler(h1)


class MaiDataManagerState(object):
    """MaiDataManagerState consolidates all the possible MDM and TPC states.
    Most of these are not needed and were removed from the actual logic.
    This was modeled loosely after the Zope.Sqlaclhemy extension.
    """
    INIT = 0
    NO_WORK = 1
    COMMITTED = 2
    ABORTED = 3
    TPC_NONE = 11
    TPC_BEGIN = 12
    TPC_VOTED = 13
    TPC_COMMITED = 14
    TPC_FINISHED = 15
    TPC_ABORTED = 16


@implementer(ISavepointDataManager)
class MailDataManager(object):
    """When creating a MailDataManager, we expect to :
        1. NOT be in a transaction on creation
        2. DO be joined into a transaction afterwards

        __init__ is given a `callable` function and `args` to pass into it.

        If everything goes as planned, during the tpc_finish phase we call:

            self.callable(*self.args)
    """
    def __init__(self, callable, args=(), onAbort=None,
                 transaction_manager=None):
        if DEBUG_FLOW : log.debug("MailDataManager.__init__")
        self.callable = callable
        self.args = args
        self.onAbort = onAbort
        if transaction_manager is None:
            transaction_manager = transaction.manager
        self.transaction_manager = transaction_manager
        self.transaction = None
        self.state = MaiDataManagerState.INIT
        self.tpc_phase = 0

    def join_transaction(self, trans=None):
        """Join the object into a transaction.

        If no transaction is specified, use ``transaction.manager.get()``.

        Raise an error if the object is already in a different transaction.
        """
        if DEBUG_FLOW : log.debug("MailDataManager.join_transaction")

        _before = self.transaction

        if trans is not None:
            _after = trans
        else:
            _after = self.transaction_manager.get()

        if _before is not None and _before is not _after:
            if self in _before._resources:
                raise ValueError("Item is in the former transaction. "
                        "It must be removed before it can be added "
                        "to a new transaction")

        if self not in _after._resources:
            _after.join(self)

        self.transaction = _after

    def _finish(self, final_state):
        if DEBUG_FLOW : log.debug("MailDataManager._finish")
        if self.transaction is None:
            raise ValueError("Not in a transaction")
        self.state = final_state

    def commit(self, trans):
        if DEBUG_FLOW : log.debug("MailDataManager.commit")
        if self.transaction is None:
            raise ValueError("Not in a transaction")
        if self.transaction is not trans:
            raise ValueError("In a different transaction")
        # OK to call ``commit`` w/ TPC underway

    def abort(self, trans):
        if DEBUG_FLOW : log.debug("MailDataManager.abort")
        if self.transaction is None:
            raise ValueError("Not in a transaction")
        if self.transaction is not trans:
            raise ValueError("In a different transaction")
        if self.tpc_phase != 0:
            raise ValueError("TPC in progress")
        if self.onAbort:
            self.onAbort()

    def sortKey(self):
        if DEBUG_FLOW : log.debug("MailDataManager.sortKey")
        return str(id(self))

    def savepoint(self):
        """Create a custom `MailDataSavepoint` object

        Although it has a `rollback` method, the custom instance doesn't
        actually do anything. `transaction` does it all.
        """
        if DEBUG_FLOW : log.debug("MailDataManager.savepoint")
        if DEBUG_FLOW : log.debug(self.transaction._resources)
        return MailDataSavepoint(self)

    def _savepoint_rollback(self, savepoint):
        """Called by the custom savepoint object `MailDataSavepoint`.

        Don't actually do anything. `transaction` does it all.
        """
        if DEBUG_FLOW : log.debug("MailDataManager._savepoint_rollback")
        if DEBUG_FLOW : log.debug(self.transaction._resources)

    ###
    ### Two Phase Support
    ###
    def tpc_begin(self, trans, subtransaction=False):
        if DEBUG_FLOW : log.debug("MailDataManager.tpc_begin | %s , %s",
                                    self.state , self.tpc_phase)
        assert trans is self.transaction, "Must not change transactions"
        assert self.tpc_phase == 0 , "Must be called outside of tpc"
        assert not subtransaction

        # begin
        self.tpc_phase = 1

    def tpc_vote(self, trans):
        if DEBUG_FLOW : log.debug("MailDataManager.tpc_vote | %s , %s",
                                  self.state , self.tpc_phase)
        assert trans is self.transaction, "Must not change transactions"
        assert self.tpc_phase == 1, "Must be called in first phase of tpc"
        # vote
        self.tpc_phase = 2

    def tpc_finish(self, trans):
        if DEBUG_FLOW : log.debug("MailDataManager.tpc_finish | %s , %s",
                                  self.state , self.tpc_phase)
        assert trans is self.transaction, "Must not change transactions"
        assert self.tpc_phase == 2, "Must be called in second phase of tpc"
        self.callable(*self.args)
        self._finish(MaiDataManagerState.TPC_FINISHED)

    def tpc_abort(self, trans):
        if DEBUG_FLOW : log.debug("MailDataManager.tpc_abort | %s , %s",
                                  self.state , self.tpc_phase)
        assert trans is self.transaction, "Must not change transactions"
        assert self.tpc_phase != 0, "Must be called inside of tpc"
        assert self.state is not MaiDataManagerState.TPC_FINISHED, "not after a commit!"
        self._finish(MaiDataManagerState.TPC_ABORTED)


@implementer(IDataManagerSavepoint)
class MailDataSavepoint:

    def __init__(self, mail_data_manager ):
        """We don't actually do anything here. transaction does it all."""
        if DEBUG_FLOW : log.debug("MailDataSavepoint.__init__")
        self.mail_data_manager = mail_data_manager

    def rollback(self):
        """We don't actually do anything here. transaction does it all."""
        if DEBUG_FLOW : log.debug("MailDataSavepoint.rollback")
        self.mail_data_manager._savepoint_rollback(self)


class AbstractMailDelivery(object):
    """Base class for mail delivery.

    Calling ``send`` will create a managed message -- the result of
    ``self.createDataManager(fromaddr,toaddrs,message)``

    The managed message should be an instance of `MailDataManager` or
    another class that implements `IDataManager` or `ISavepointDataManager`

    The managed message is immediately joined into the current transaction.
    """
    transaction_manager = transaction.manager

    def send(self, fromaddr, toaddrs, message):
        if DEBUG_FLOW : log.debug("AbstractMailDelivery.send")
        assert isinstance(message, Message), \
               'Message must be instance of email.message.Message'
        encoding.cleanup_message(message)
        messageid = message['Message-Id']
        if messageid is None:
            messageid = message['Message-Id'] = make_msgid('repoze.sendmail')
        if message['Date'] is None:
            message['Date'] = formatdate()
        managedMessage = self.createDataManager(fromaddr, toaddrs, message)
        managedMessage.join_transaction()
        return messageid


@implementer(IMailDelivery)
class DirectMailDelivery(AbstractMailDelivery):

    def __init__(self, mailer):
        if DEBUG_FLOW : log.debug("DirectMailDelivery.__init__")
        self.mailer = mailer

    def createDataManager(self, fromaddr, toaddrs, message):
        if DEBUG_FLOW : log.debug("DirectMailDelivery.createDataManager")
        return MailDataManager(self.mailer.send,
                               args=(fromaddr, toaddrs, message),
                               transaction_manager=self.transaction_manager)


@implementer(IMailDelivery)
class QueuedMailDelivery(AbstractMailDelivery):

    queuePath = property(lambda self: self._queuePath)
    processor_thread = None

    def __init__(self, queuePath):
        if DEBUG_FLOW : log.debug("QueuedMailDelivery.__init__")
        self._queuePath = queuePath

    def createDataManager(self, fromaddr, toaddrs, message):
        if DEBUG_FLOW : log.debug("QueuedMailDelivery.createDataManager")
        message = copy_message(message)
        message['X-Actually-From'] = Header(fromaddr, 'utf-8')
        message['X-Actually-To'] = Header(','.join(toaddrs), 'utf-8')
        maildir = Maildir(self.queuePath, True)
        tx_message = maildir.add(message)
        return MailDataManager(tx_message.commit, onAbort=tx_message.abort,
                               transaction_manager=self.transaction_manager)


def copy_message(message):
    parser = Parser()
    return parser.parsestr(message.as_string())
