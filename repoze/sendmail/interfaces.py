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
"""`repoze.sendmail` interfaces

Sending e-mail from and applications works as follows:

- An application locates a mail delivery utility (`IMailDelivery`).
  Applications may also instantiate a particular delivery class directly.

- The application feeds a message to the delivery instance, geting back a
  unique message ID. 

- The deliver registers with the transaction system to make sure the
  message is only sent when the transaction commits successfully.  Among
  other things this avoids duplicate messages on `ConflictErrors`.

- A queuing delivery puts the message into a queue (a Maildir mailbox in
  the filesystem). A separate process or thread watches the queue and
  delivers messages asynchronously.  Since the queue is located in the
  filesystem, it survives application restarts or crashes and the mail is not
  lost.  The queue processor can implement batching to keep the server load low.

- A direct delivery delivers messages synchronously via SMPT during the
  transaction commit..

- The queue processor and the direct delivery actually delivers the
  messages by using a mailer (`IMailer`) component that encapsulates the
  delivery process.  The package provides two mailers:

    - `SMTPMailer` sends all messages to a relay host using SMTP

    - 'SendmailMailer` sends all messages using the `sendmail` command.
"""

from zope.interface import Attribute, Interface

class IMailDelivery(Interface):
    """Send an email to a group of people.
    """

    transaction_manager = Attribute("The transaction manager to use.")

    def send(fromaddr, toaddrs, message):
        """Send an email message.

        `fromaddr` is the sender address (byte string),

        `toaddrs` is a sequence of recipient addresses (byte strings).

        `message` is a `Message` object from the stdlib
        `email.message` module.  If it does not contain a Message-Id
        header, one will be generated and added automatically.

        Returns the message ID.

        Messages are actually sent during transaction commit.
        """

class IMailer(Interface):
    """Handles synchronous mail delivery.
    """
    def send(fromaddr, toaddrs, message):
        """Send an email message.

        `fromaddr` is the sender address (unicode string),

        `toaddrs` is a sequence of recipient addresses (unicode strings).

        `message` is a `Message` object from the stdlib
        `email.message` module.  If it does not contain a Message-Id
        header, one will be generated and added automatically.

        Messages are sent immediatelly.
        """
