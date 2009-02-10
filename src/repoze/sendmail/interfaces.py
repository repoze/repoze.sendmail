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

$Id: interfaces.py 79091 2007-08-21 18:35:51Z andreasjung $
"""
__docformat__ = 'restructuredtext'

from zope.interface import Interface, Attribute
from zope.schema import TextLine, Int, Password, Bool

from zope.i18nmessageid import MessageFactory
_ = MessageFactory('zope')


class IMailDelivery(Interface):
    """A mail delivery utility allows someone to send an email to a group of
    people."""

    def send(fromaddr, toaddrs, message):
        """Send an email message.

        `fromaddr` is the sender address (byte string),

        `toaddrs` is a sequence of recipient addresses (byte strings).

        `message` is a byte string that contains both headers and body
        formatted according to RFC 2822.  If it does not contain a Message-Id
        header, it will be generated and added automatically.

        Returns the message ID.

        You can subscribe to `IMailEvent` events for notification about
        problems or successful delivery.

        Messages are actually sent during transaction commit.
        """


class IDirectMailDelivery(IMailDelivery):
    """A mail delivery utility that delivers messages synchronously during
    transaction commit.

    Not useful for production use, but simpler to set up and use.
    """

    mailer = Attribute("IMailer that is used for message delivery")


class IQueuedMailDelivery(IMailDelivery):
    """A mail delivery utility that puts all messages into a queue in the
    filesystem.

    Messages will be delivered asynchronously by a separate component.
    """

    queuePath = TextLine(
        title=_(u"Queue path"),
        description=_(u"Pathname of the directory used to queue mail."))


class IMailQueueProcessor(Interface):
    """A mail queue processor that delivers queueud messages asynchronously.
    """

    queuePath = TextLine(
        title=_(u"Queue Path"),
        description=_(u"Pathname of the directory used to queue mail."))

    pollingInterval = Int(
        title=_(u"Polling Interval"),
        description=_(u"How often the queue is checked for new messages"
                       " (in milliseconds)"),
        default=5000)

    mailer = Attribute("IMailer that is used for message delivery")


class IMailer(Interface):
    """Mailer handles synchronous mail delivery."""

    def send(fromaddr, toaddrs, message):
        """Send an email message.

        `fromaddr` is the sender address (unicode string),

        `toaddrs` is a sequence of recipient addresses (unicode strings).

        `message` contains both headers and body formatted according to RFC
        2822.  It should contain at least Date, From, To, and Message-Id
        headers.

        Messages are sent immediatelly.

        Dispatches an `IMailSentEvent` on successful delivery, otherwise an
        `IMailErrorEvent`.
        """


class ISMTPMailer(IMailer):
    """A mailer that delivers mail to a relay host via SMTP."""

    hostname = TextLine(
        title=_(u"Hostname"),
        description=_(u"Name of server to be used as SMTP server."))

    port = Int(
        title=_(u"Port"),
        description=_(u"Port of SMTP service"),
        default=25)

    username = TextLine(
        title=_(u"Username"),
        description=_(u"Username used for optional SMTP authentication."))

    password = Password(
        title=_(u"Password"),
        description=_(u"Password used for optional SMTP authentication."))

    no_tls = Bool(
        title=_(u"No TLS"),
        description=_(u"Never use TLS for sending email."))

    force_tls = Bool(
        title=_(u"Force TLS"),
        description=_(u"Use TLS always for sending email."))


class IMailEvent(Interface):
    """Generic mail event."""

    messageId = Attribute("Message id according to RFC 2822")


class IMailSentEvent(IMailEvent):
    """Event that is fired when a message is succesfully sent.

    This does not mean that all the recipients have received it, it only
    means that the message left this system successfully.  It is possible
    that a bounce message will arrive later from some remote mail server.
    """


class IMailErrorEvent(IMailEvent):
    """Event that is fired when a message cannot be delivered."""

    errorMessage = Attribute("Error message")



class IMaildirFactory(Interface):

    def __call__(dirname, create=False):
        """Opens a `Maildir` folder at a given filesystem path.

        If `create` is ``True``, the folder will be created when it does not
        exist.  If `create` is ``False`` and the folder does not exist, an
        exception (``OSError``) will be raised.

        If path points to a file or an existing directory that is not a
        valid `Maildir` folder, an exception is raised regardless of the
        `create` argument.
        """


class IMaildir(Interface):
    """Read/write access to `Maildir` folders.

    See http://www.qmail.org/man/man5/maildir.html for detailed format
    description.
    """

    def __iter__():
        """Returns an iterator over the pathnames of messages in this folder.
        """

    def newMessage():
        """Creates a new message in the `maildir`.

        Returns a file-like object for a new file in the ``tmp`` subdirectory
        of the `Maildir`.  After writing message contents to it, call the
        ``commit()`` or ``abort()`` method on it.

        The returned object implements `IMaildirMessageWriter`.
        """


class IMaildirMessageWriter(Interface):
    """A file-like object to a new message in a `Maildir`."""

    def write(str):
        """Writes a string to the file.

        There is no return value. Due to buffering, the string may not actually
        show up in the file until the ``commit()`` method is called.
        """

    def writelines(sequence):
        """Writes a sequence of strings to the file.

        The sequence can be any iterable object producing strings, typically a
        list of strings. There is no return value.  ``writelines`` does not add
        any line separators.
        """

    def close():
        """Closes the message file.

        No further writes are allowed.  You can call ``close()`` before calling
        ``commit()`` or ``abort()`` to avoid having too many open files.

        Calling ``close()`` more than once is allowed.
        """

    def commit():
        """Commits the new message using the `Maildir` protocol.

        First, the message file is flushed, closed, then it is moved from
        ``tmp`` into ``new`` subdirectory of the maildir.

        Calling ``commit()`` more than once is allowed.
        """

    def abort():
        """Aborts the new message.

        The message file is closed and removed from the ``tmp`` subdirectory
        of the `maildir`.

        Calling ``abort()`` more than once is allowed.
        """

