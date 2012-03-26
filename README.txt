===============
repoze.sendmail
===============

`repoze.sendmail` allows coupling the sending of email messages with a
transaction, using the Zope transaction manager.  This allows messages to
only be sent out when and if a transaction is committed, preventing users
from receiving notifications about events which may not have completed
successfully.  Messages may be sent directly or stored in a queue for later
sending.  The queued mail approach is the more common and recommended path.  A
console application which can flush the queue, sending the messages that it
finds, is included for convenience.

`repoze.sendmail` is a fork of `zope.sendmail`.  Functionality that was
specific to running in a Zope context has been removed, making this version
more generally useful to users of other frameworks.

Note that repoze.sendmail works only under Python 2.5+ (it will not work
under 2.4) and Python 3.2+.  Note that the ``transaction`` package, which
this package depends on, must be less than 1.2 to work under Python 2.5 (1.2
is 2.6-and-better).

==============
Basic Tutorial
==============

Messages are sent by means of a `Delivery` object. Two deliveries are included
in `repoze.sendmail.delivery`: `QueuedMailDelivery` and `DirectMailDelivery`.
A delivery implements the interface defined by
`repoze.sendmail.interfaces.IDelivery`, which consists of a single `send`
method::

   def send(fromaddr, toaddrs, message):
       """ Sends message on transaction commit. """

`fromaddr` is the address of the sender of the message.  `toaddrs` is a list of
email addresses for recipients of the message.  `message` must be an instance
`email.message.Message` and is the actual message which will be sent.

To create a queued delivery::

   from email.message import Message
   from repoze.sendmail.delivery import QueuedMailDelivery

   message = Message()
   message['From'] = 'Chris <chris@example.com>'
   message['To'] = 'Paul <paul@example.com>, Tres <tres@example.com>'
   message['Subject'] = "repoze.sendmail is a useful package"
   message.set_payload("The subject line says it all.")

   delivery = QueuedMailDelivery('path/to/queue')
   delivery.send('chris@example.com', ['paul@example.com', 'tres@example.com'],
                 message)

The message will be added to the maildir queue in 'path/to/queue' when and if
the current transaction is committed successsfully.

`repoze.sendmail` includes a console app utility for sending queued messages::

  $ bin/qp path/to/queue

This will attempt to use an SMTP server at localhost to send any messages found
in the queue.  To see all options available::

  $ bin/qp --help

Direct delivery can also be used::

   from repoze.sendmail.delivery import DirectMailDelivery
   from repoze.sendmail.mailer import SMTPMailer

   mailer = SMTPMailer()  # Uses localhost, port 25 be default.
   delivery = DirectMailDelivery(mailer)
   delivery.send('chris@example.com', ['paul@example.com', 'tres@example.com'],
                 message)

repoze.sendmail hooks into the Zope transaction manager and only sends
messages on transaction commit. If you are using a framework which, like
`repoze.bfg`, does not use transactions by default, you will need to begin and
commit a transaction of your own in order for mail to be sent::

  import transaction
  transaction.manager.begin()
  try:
      my_code_here()
      transaction.manager.commit()
  except e:
      transaction.manager.abort()
      raise e
