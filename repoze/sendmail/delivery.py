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
from transaction.interfaces import ISavepointDataManager
from transaction.interfaces import IDataManagerSavepoint
import transaction

import logging
log = logging.getLogger(__name__)


DEBUG_FLOW = False 
if DEBUG_FLOW :
    import sys
    log.setLevel(logging.DEBUG)
    h1 = logging.StreamHandler(sys.stdout)
    log.addHandler(h1)


    
class MaiDataManagerState(object):
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


def is_resource_in_transaction(resource,trans):
    if resource in trans._resources :
        return True
    return False



@implementer(ISavepointDataManager)
class MailDataManager(object):

    def __init__(self, callable, args=(), onAbort=None):
        """We expect to :
            1. NOT be in a transaction on creation
            2. DO be joined into a transaction
        """
        if DEBUG_FLOW : log.debug("MailDataManager.__init__")
        self.callable = callable
        self.args = args

        # Use the default thread transaction manager.
        self.transaction_manager = transaction.manager

        # Our transaction state:
        self.transaction = None

        #   What state are we in
        self.state = MaiDataManagerState.INIT

        #   What phase, if any, of two-phase commit we are in:
        self.tpc_phase = 0
        
        # store the onAbort
        self.onAbort = onAbort
        

    def join_transaction(self,trans=None):
        if DEBUG_FLOW : log.debug("MailDataManager.join_transaction")
        
        # are we specifying a transaction to join ?
        if trans is not None:
            self.transaction = trans

        # If this is the first change in the transaction, join the transaction
        if self.transaction is None :
            self.transaction = self.transaction_manager.get()

        # only join a transaction ONCE
        if not is_resource_in_transaction( self , self.transaction ):
            self.transaction.join(self)
            

    def _finish(self,final_state):
        if DEBUG_FLOW : log.debug("MailDataManager._finish")
        assert self.transaction is not None
        self.state = final_state
        self._resetTransaction()
    

    def _resetTransaction(self):
        if DEBUG_FLOW : log.debug("MailDataManager._resetTransaction")
        self.last_note = getattr(self.transaction, 'description', None)
        self.transaction = None

        self.state = MaiDataManagerState.INIT
        self.tpc_phase = 0


    def commit( self, trans ):
        if DEBUG_FLOW : log.debug("MailDataManager.commit")
        pass
        
    


    def abort(self, trans):
        """Throw away changes made before the commit process has started
        """
        if DEBUG_FLOW : log.debug("MailDataManager.abort")
        assert (self.transaction is not None), "Must have transaction"
        assert (trans is self.transaction), "Must not change transactions"
        assert is_resource_in_transaction( self , self.transaction ) , "Must be in the transaction"
        assert (self.tpc_phase == 0), "Must be called outside of tpc"

        self._resetTransaction()

        if self.onAbort:
            self.onAbort()


    def sortKey(self):
        if DEBUG_FLOW : log.debug("MailDataManager.sortKey")
        return str(id(self))


    # No subtransaction support ?
    def abort_sub(self, trans):
        raise ValueError("abort_sub")
        pass  #pragma NO COVERAGE


    # No subtransaction support ?
    def commit_sub(self, trans):
        raise ValueError("commit_sub")
        pass  #pragma NO COVERAGE



    ###
    ### Savepoint Support
    ###

    def savepoint(self):
        if DEBUG_FLOW : log.debug("MailDataManager.savepoint")
        if DEBUG_FLOW : log.debug(self.transaction._resources)
        #
        #   we create a custom MailDataSavepoint object , which just has a rollback
        #   the custom instance doesn't actually do anything. transaction does it all.
        #
        return MailDataSavepoint(self)

    def _savepoint_rollback(self, savepoint):
        if DEBUG_FLOW : log.debug("MailDataManager._savepoint_rollback")
        if DEBUG_FLOW : log.debug(self.transaction._resources)
        #
        #   called by the custom savepoint MailDataSavepoint
        #   this doesn't actually do anything. transaction does it all.
        #



    ###
    ### Two Phase Support
    ###



    def tpc_begin(self, trans, subtransaction=False):
        if DEBUG_FLOW : log.debug("MailDataManager.tpc_begin | %s , %s" , self.state , self.tpc_phase)
        assert trans is self.transaction, "Must not change transactions"
        assert self.tpc_phase == 0 , "Must be called outside of tpc"
        assert not subtransaction

        # begin
        self.tpc_phase = 1


    def tpc_vote(self, trans):
        if DEBUG_FLOW : log.debug("MailDataManager.tpc_vote | %s , %s" , self.state , self.tpc_phase)
        assert trans is self.transaction, "Must not change transactions"
        assert self.tpc_phase == 1, "Must be called in first phase of tpc"

        # vote
        self.tpc_phase = 2


    def tpc_finish(self, trans):
        if DEBUG_FLOW : log.debug("MailDataManager.tpc_finish | %s , %s" , self.state , self.tpc_phase)
        assert trans is self.transaction, "Must not change transactions"
        assert self.tpc_phase == 2, "Must be called in second phase of tpc"
        
        self.callable(*self.args)

        self._finish(MaiDataManagerState.TPC_FINISHED)


    def tpc_abort(self, trans):
        if DEBUG_FLOW : log.debug("MailDataManager.tpc_abort | %s , %s" , self.state , self.tpc_phase)
        assert trans is self.transaction, "Must not change transactions"
        assert self.tpc_phase != 0, "Must be called inside of tpc"
        assert self.state is not MaiDataManagerState.COMMITTED, "not in a commit!"
        
        self._finish(MaiDataManagerState.TPC_ABORTED)



@implementer( transaction.interfaces.IDataManagerSavepoint )
class MailDataSavepoint:

    def __init__(self, mail_data_manager ):
        #
        #   we don't actually do anything here. transaction does it all.
        #
        if DEBUG_FLOW : log.debug("MailDataSavepoint.__init__")
        self.mail_data_manager = mail_data_manager


    def rollback(self):
        #
        #   we don't actually do anything here. transaction does it all.
        #
        if DEBUG_FLOW : log.debug("MailDataSavepoint.rollback")
        self.mail_data_manager._savepoint_rollback(self)




class AbstractMailDelivery(object):

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
                               args=(fromaddr, toaddrs, message))


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
        return MailDataManager(tx_message.commit, onAbort=tx_message.abort)


def copy_message(message):
    parser = Parser()
    return parser.parsestr(message.as_string())


