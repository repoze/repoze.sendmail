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
"""Mailer interfaces

Email sending from Zope 3 applications works as follows:

- A Zope 3 application locates a mail delivery utility (`IMailDelivery`) and
  feeds a message to it. It gets back a unique message ID so it can keep
  track of the message by subscribing to `IMailEvent` events.

- The utility registers with the transaction system to make sure the
  message is only sent when the transaction commits successfully.  (Among
  other things this avoids duplicate messages on `ConflictErrors`.)

- If the delivery utility is a `IQueuedMailDelivery`, it puts the message into
  a queue (a Maildir mailbox in the file system). A separate process or thread
  (`IMailQueueProcessor`) watches the queue and delivers messages
  asynchronously. Since the queue is located in the file system, it survives
  Zope restarts or crashes and the mail is not lost.  The queue processor
  can implement batching to keep the server load low.

- If the delivery utility is a `IDirectMailDelivery`, it delivers messages
  synchronously during the transaction commit.  This is not a very good idea,
  as it makes the user wait.  Note that transaction commits must not fail,
  but that is not a problem, because mail delivery problems dispatch an
  event instead of raising an exception.

  However, there is a problem -- sending events causes unknown code to be
  executed during the transaction commit phase.  There should be a way to
  start a new transaction for event processing after this one is commited.

- An `IMailQueueProcessor` or `IDirectMailDelivery` actually delivers the
  messages by using a mailer (`IMailer`) component that encapsulates the
  delivery process.  There currently is only one mailer:

    - `ISMTPMailer` sends all messages to a relay host using SMTP

- If mail delivery succeeds, an `IMailSentEvent` is dispatched by the mailer.
  If mail delivery fails, no exceptions are raised, but an `IMailErrorEvent` is
  dispatched by the mailer.
"""

from zope.interface import Interface

class IMailDelivery(Interface):
    """A mail delivery utility allows someone to send an email to a group of
    people."""

    def send(fromaddr, toaddrs, message):
        """Send an email message.

        `fromaddr` is the sender address (byte string),

        `toaddrs` is a sequence of recipient addresses (byte strings).

        `message` is a `Message` object from the stdlib
        `email.message` module.  If it does not contain a Message-Id
        header, it will be generated and added automatically.

        Returns the message ID.

        You can subscribe to `IMailEvent` events for notification about
        problems or successful delivery.

        Messages are actually sent during transaction commit.
        """


class IMailer(Interface):
    """Mailer handles synchronous mail delivery."""

    def send(fromaddr, toaddrs, message):
        """Send an email message.

        `fromaddr` is the sender address (unicode string),

        `toaddrs` is a sequence of recipient addresses (unicode strings).

        `message` is a `Message` object from the stdlib
        `email.message` module.  If it does not contain a Message-Id
        header, it will be generated and added automatically.

        Messages are sent immediatelly.

        Dispatches an `IMailSentEvent` on successful delivery, otherwise an
        `IMailErrorEvent`.
        """
