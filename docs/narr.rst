repoze.sendmail
===============

:mod:`repoze.sendmail` allows coupling the sending of email messages with a
transaction, using the Zope transaction manager.  This allows messages to
only be sent out when and if a transaction is committed, preventing users
from receiving notifications about events which may not have completed
successfully.  Messages may be sent directly or stored in a queue for later
sending.  The queued mail approach is the more common and recommended path.
For convenience, the package includes a console application which can flush
the queue, sending the messages that it finds.

:mod:`repoze.sendmail` is a fork of :mod:`zope.sendmail`.  Functionality that
was specific to running in a Zope context has been removed, making this
version more generally useful to users of other frameworks.

Note that :mod:`repoze.sendmail` works only under Python 2.6+ and Python 3.2+.

Delivering Mail Messages from Application Code
----------------------------------------------

Messages are sent by means of a `Delivery` object. :mod:`repoze.sendmail`
include Two delivery implementations:

- :class:`repoze.sendmail.delivery.QueuedMailDelivery`
- :class:`repoze.sendmail.delivery.DirectMailDelivery`

A delivery implements the interface defined by
:class:`repoze.sendmail.interfaces.IDelivery`.  That interface defines
a single `send` method:

.. code-block:: python

   def send(fromaddr, toaddrs, message):
       """ Sends message on transaction commit. """

- `fromaddr` is the address of the sender of the message.
- `toaddrs` is a list of email addresses for recipients of the message.
- `message` must be an instance of :class:`email.message.Message` and is the
  actual message which will be sent.


Delivery via a Mail Queue
-------------------------

To create a queued delivery:

.. code-block:: python

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

:mod:`repoze.sendmail` includes a console app utility for sending queued
messages:

.. code-block:: bash

  $ bin/qp path/to/queue

This will attempt to use an SMTP server at localhost to send any messages found
in the queue.  To see all options available:

.. code-block:: bash

  $ bin/qp --help
  
The QueueProcessor used by the console utility can also be called from Python:

.. code-block:: python

   qp = QueueProcessor(mailer, queue_path, ignore_transient=True)
   qp.send_messages()
   
The `ignore_transient` parameter, when True, will cause the queue processor to
ignore transient errors (any error code not between 500 and 599). This is
useful when monitoring systems are used, to prevent filling the error reports
with temporary errors.


Direct SMTP Delivery
--------------------

Direct delivery (using the SMTP protocol) can also be used:

.. code-block:: python

   from repoze.sendmail.delivery import DirectMailDelivery
   from repoze.sendmail.mailer import SMTPMailer

   mailer = SMTPMailer()  # Uses localhost, port 25 be default.
   delivery = DirectMailDelivery(mailer)
   delivery.send('chris@example.com', ['paul@example.com', 'tres@example.com'],
                 message)


Delivery via the :command:`sendmail` Command
--------------------------------------------

If you are on a Unix/BSD machine and prefer to use the standard unix `sendmail`
interface ( which is likely provided by exim, postfix or qmail ) via a binary
at '/usr/sbin/sendmail' you can simply opt to use the following classes :

.. code-block:: python

   mailer = SendmailMailer()
   delivery = DirectMailDelivery(mailer)

you may also customize this delivery with the location of another binary:

.. code-block:: python

   mailer = SendmailMailer(sendmail_app='/usr/local/bin/sendmail')


Transaction Integration
-----------------------

:mod:`repoze.sendmail` hooks into the Zope transaction manager and only
sends messages on transaction commit. If you are using a framework which does
not use transactions by default, you will need to begin and commit a
transaction of your own in order for mail to be sent::

  import transaction
  transaction.manager.begin()
  try:
      my_code_here()
      transaction.manager.commit()
  except e:
      transaction.manager.abort()
      raise e

