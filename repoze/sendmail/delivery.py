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

#
# DEBUG_FLOW is useful when mapping out the interactions with `transaction`
# It just prints out the current function name / state
#
DEBUG_FLOW = False 
if DEBUG_FLOW :
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


def is_resource_in_transaction(resource,trans):
    """Early versions of this package immediately joined a MDM into a 
    transaction:
        > transaction.get().join( createDataManager() )
    This behavior was harder to test with , and it was easy to add an object 
    into a transaction multiple times.  The `transaction` package doesn't raise 
    an error if that happens, so random errors with the TPC state occur as the 
    same element has every phase called multiple times.
    """
    if resource in trans._resources :
        return True
    return False



@implementer(ISavepointDataManager)
class MailDataManager(object):

    def __init__(self, callable, args=(), onAbort=None):
        """When creating a MailDataManager, we expect to :
            1. NOT be in a transaction on creation
            2. DO be joined into a transaction afterwards
            
            __init__ is given a `callable` function and `args` to pass into it.
            
            if everything goes as planned, during the tpc_finish phase we call:
            
                self.callable(*self.args)
            
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
        """join the object into a transaction.  
        if no transaction is specified, it will call `transaction.manager.get()`
        if the object is already in a transaction, it will raise an error.
        
        """
        if DEBUG_FLOW : log.debug("MailDataManager.join_transaction")
        
        _transaction_old = self.transaction
        
        # are we specifying a transaction to join ?
        if trans is not None:
            self.transaction = trans
        # if we haven't specified the transactions, join the current one
        else:
            self.transaction = self.transaction_manager.get()
            
        # if we changed transactions...
        if _transaction_old and ( _transaction_old != self.transaction ) :
            if is_resource_in_transaction( self , _transaction_old ):
                raise ValueError("""Item is in the former transaction. It must\
                be removed before it can be added to a new transaction""")

        # only join the transaction ONCE; if we're already in it, no worries.
        if not is_resource_in_transaction( self , self.transaction ):
            self.transaction.join(self)
        

    def _finish(self,final_state):
        """this method might not be needed"""
        if DEBUG_FLOW : log.debug("MailDataManager._finish")
        assert self.transaction is not None
        self.state = final_state
    

    def _resetState(self):
        """this method might not be needed"""
        if DEBUG_FLOW : log.debug("MailDataManager._resetState")
        self.tpc_phase = 0
        self.state = MaiDataManagerState.INIT



    def commit( self, trans ):
        if DEBUG_FLOW : log.debug("MailDataManager.commit")
        pass
        
    


    def abort(self, trans):
        """Throw away changes made before the commit process has started
        
        """
        if DEBUG_FLOW : log.debug("MailDataManager.abort")
        assert (self.transaction is not None), "Must have transaction"
        assert (trans is self.transaction), "Must not change transactions"
        assert (self.tpc_phase == 0), "Must be called outside of tpc"

        ## the following was used for testing:
        ##   we might not be in the transaction
        ##   if we've already been removed, we still seem to be listening in for 
        ##   the events.  this only seems to happen during multiple levels of 
        ##   nested transactions
        # assert is_resource_in_transaction( self , self.transaction ) , "Must be in the transaction"

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
        """we create a custom `MailDataSavepoint` object , which has a 
        `rollback` method.
        the custom instance doesn't actually do anything. `transaction` does it 
        all.
        """
        if DEBUG_FLOW : log.debug("MailDataManager.savepoint")
        if DEBUG_FLOW : log.debug(self.transaction._resources)
        return MailDataSavepoint(self)

    def _savepoint_rollback(self, savepoint):
        """called by the custom savepoint object `MailDataSavepoint`
        this doesn't actually do anything. `transaction` does it all."""
        if DEBUG_FLOW : log.debug("MailDataManager._savepoint_rollback")
        if DEBUG_FLOW : log.debug(self.transaction._resources)



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
        assert self.state is not MaiDataManagerState.TPC_FINISHED, "not after a commit!"
        
        self._finish(MaiDataManagerState.TPC_ABORTED)



@implementer( transaction.interfaces.IDataManagerSavepoint )
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
    
        calling `send` will create a managed message -- the result of 
            `self.createDataManager(fromaddr,toaddrs,message)`
        
        The managed message should be an instance of `MailDataManager` or
        another class that implements `IDataManager` or `ISavepointDataManager`
        
        The managed message is immediately joined into the current transaction.
    """

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


