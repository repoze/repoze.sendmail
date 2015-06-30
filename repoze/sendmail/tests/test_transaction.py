import logging
import unittest

from repoze.sendmail.delivery import DirectMailDelivery
import transaction
from email.message import Message



class TestTransactionMails(unittest.TestCase):

    def setUp(self):
        transaction.begin()

    def test_abort(self):
        mailer = _makeMailerStub()
        delivery = DirectMailDelivery(mailer)

        ( fromaddr , toaddrs ) = fromaddr_toaddrs()
        message = sample_message()
        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assertEqual(msgid, '<20030519.1234@example.org>')
        self.assertEqual(mailer.sent_messages, [])
        transaction.abort()
        transaction.commit()
        self.assertEqual(mailer.sent_messages,[])


    def test_doom(self):
        mailer = _makeMailerStub()
        delivery = DirectMailDelivery(mailer)

        ( fromaddr , toaddrs ) = fromaddr_toaddrs()
        message = sample_message()
        msgid = delivery.send(fromaddr, toaddrs, message)
        self.assertEqual(msgid, '<20030519.1234@example.org>')
        self.assertEqual(mailer.sent_messages, [])
        transaction.doom()
        transaction.abort()
        transaction.commit()
        self.assertEqual(mailer.sent_messages, [])



    def test_savepoint(self):
        mailer = _makeMailerStub()
        delivery = DirectMailDelivery(mailer)
        ( fromaddr , toaddrs ) = fromaddr_toaddrs()
        
        bodies_good = {}
        bodies_bad = {}
        for i in ( 1,3,5, ):
            bodies_good[i] = 'Sample Body - %s | Good' % i
        for i in ( 2,4,6, ):
            bodies_bad[i] = 'Sample Body - %s | Bad' % i
            
        bodies_all = dict(list(bodies_good.items()) +
                          list(bodies_bad.items()))

        transaction.begin()
        for i in range(1,7) :
            sp = transaction.savepoint()
            body = bodies_all[i]
            message = sample_message(body=body)
            msgid = delivery.send(fromaddr, toaddrs, message)
            self.assertEqual(msgid, '<20030519.1234@example.org>')
            self.assertEqual(mailer.sent_messages, [])
            if i in bodies_bad :
                sp.rollback()
        
        # we shouldn't have sent anything
        self.assertEqual(mailer.sent_messages, [])
        
        # so now let's commit
        transaction.commit()
        
        # make sure we have the right number of messages
        self.assertEqual(len(mailer.sent_messages), len(bodies_good.values()))

        # generate our expected body
        bodies_expected = bodies_good.values()

        # make sure our bodies are only good        
        for f, t, m in mailer.sent_messages :
            self.assertTrue(m._payload in bodies_expected)

        ## ok, can we do multiple savepoints ?
        active_transaction = transaction.manager.get()

        mailer.sent_messages = []
        transaction.begin()
        sp_outer = transaction.savepoint()
        for i in range(1,7) :
            sp = transaction.savepoint()
            body = bodies_all[i]
            message = sample_message(body=body)
            msgid = delivery.send(fromaddr, toaddrs, message)
            self.assertEqual(msgid, '<20030519.1234@example.org>')
            self.assertEqual(mailer.sent_messages, [])
            sp3 = transaction.savepoint()
            sp3.rollback()
            if i in bodies_bad :
                sp.rollback()
        sp_outer.rollback()

    def test_abort_after_failed_commit(self):
        # It should be okay to call transaction.abort() after a failed
        # commit.  (E.g. pyramid_tm does this.)

        mailer = _makeMailerStub(_failing=True)
        delivery = DirectMailDelivery(mailer)
        fromaddr, toaddrs = fromaddr_toaddrs()
        message = sample_message()
        delivery.send(fromaddr, toaddrs, message)

        with DummyLogHandler():  # Avoid "no handler could be found" on stderr
            self.assertRaises(SendFailed, transaction.commit)

        # An abort after commit failure should not raise exceptions
        transaction.abort()

    def test_commit_fails_before_tpc_vote(self):
        # If there is a failure during transaction.commit() before all
        # data managers have voted, .abort() is called on the non-voted
        # managers before their .tpc_finish() is called.

        mailer = _makeMailerStub()
        delivery = DirectMailDelivery(mailer)
        fromaddr, toaddrs = fromaddr_toaddrs()
        message = sample_message()
        delivery.send(fromaddr, toaddrs, message)

        # Add another data manager whose tpc_vote fails before our
        # delivery's tpc_vote gets called.
        failing_dm = FailingDataManager(sort_key='!!! run first')
        transaction.get().join(failing_dm)

        try:
            self.assertRaises(VoteFailure, transaction.commit)
            self.assertEqual(mailer.sent_messages, [])
        finally:
            transaction.abort()


def sample_message( body="This is just an example"):
    ( fromaddr , toaddrs ) = fromaddr_toaddrs()
    message = Message()
    message['From'] = fromaddr
    message['To'] = 'some-zope-coders:;'
    message['Date'] = 'Date: Mon, 19 May 2003 10:17:36 -0400'
    message['Message-Id'] = ext_msgid = '<20030519.1234@example.org>'
    message['Subject'] = 'example'
    message.set_payload(body)
    return message
    
def fromaddr_toaddrs():
    fromaddr = 'Jim <jim@example.com>'
    toaddrs = ('Guido <guido@example.com>',
               'Steve <steve@examplecom>')
    return ( fromaddr , toaddrs )


class SendFailed(Exception):
    pass


def _makeMailerStub(*args, **kw):
    from zope.interface import implementer
    from repoze.sendmail.interfaces import IMailer

    @implementer(IMailer)
    class MailerStub(object):
        def __init__(self, *args, **kw):
            self.failing = kw.get('_failing', False)
            self.sent_messages = []

        def send(self, fromaddr, toaddrs, message):
            if self.failing:
                raise SendFailed("send failed")
            self.sent_messages.append((fromaddr, toaddrs, message))

    return MailerStub(*args, **kw)


class VoteFailure(Exception):
    pass


class FailingDataManager(object):
    def __init__(self, sort_key):
        self.sort_key = sort_key

    def sortKey(self):
        return self.sort_key

    def abort(self, trans):
        pass

    def tpc_begin(self, trans):
        pass

    def commit(self, trans):
        pass

    def tpc_vote(self, trans):
        raise VoteFailure("vote failed")

    def tpc_abort(self, trans):
        pass


class DummyLogHandler(logging.Handler):
    def emit(self, record):
        pass

    def __enter__(self):
        root_logger = logging.getLogger()
        root_logger.addHandler(self)

    def __exit__(self, typ, value, tb):
        root_logger = logging.getLogger()
        root_logger.removeHandler(self)
