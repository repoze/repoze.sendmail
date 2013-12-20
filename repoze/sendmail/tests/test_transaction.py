import unittest

from repoze.sendmail.delivery import DirectMailDelivery
from email.message import Message



class TestTransactionMails(unittest.TestCase):

    def test_abort(self):
        import transaction
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
        import transaction
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
        import transaction
        
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

