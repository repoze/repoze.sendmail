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
"""Mail Delivery utility implementation

This module contains various implementations of `MailDeliverys`.

$Id: delivery.py 92774 2008-11-04 12:46:08Z adamg $
"""
__docformat__ = 'restructuredtext'

import atexit
import logging
import os
import os.path
import rfc822
import smtplib
import stat
import threading
import time
from cStringIO import StringIO
from random import randrange
from time import strftime
from socket import gethostname

from zope.interface import implements
from repoze.sendmail.interfaces import IDirectMailDelivery, IQueuedMailDelivery
from repoze.sendmail.maildir import Maildir
from transaction.interfaces import IDataManager
import transaction

import sys
if sys.platform == 'win32':
    import win32file
    _os_link = lambda src, dst: win32file.CreateHardLink(dst, src, None)
else:
    _os_link = os.link

# The longest time sending a file is expected to take.  Longer than this and
# the send attempt will be assumed to have failed.  This means that sending
# very large files or using very slow mail servers could result in duplicate
# messages sent.
MAX_SEND_TIME = 60*60*3

class MailDataManager(object):
    implements(IDataManager)

    def __init__(self, callable, args=(), onAbort=None):
        self.callable = callable
        self.args = args
        self.onAbort = onAbort
        # Use the default thread transaction manager.
        self.transaction_manager = transaction.manager

    def commit(self, transaction):
        pass

    def abort(self, transaction):
         if self.onAbort:
            self.onAbort()

    def sortKey(self):
        return id(self)

    # No subtransaction support.
    def abort_sub(self, transaction):
        pass

    commit_sub = abort_sub

    def beforeCompletion(self, transaction):
        pass

    afterCompletion = beforeCompletion

    def tpc_begin(self, transaction, subtransaction=False):
        assert not subtransaction

    def tpc_vote(self, transaction):
        pass

    def tpc_finish(self, transaction):
        self.callable(*self.args)

    tpc_abort = abort


class AbstractMailDelivery(object):

    def newMessageId(self):
        """Generates a new message ID according to RFC 2822 rules"""
        randmax = 0x7fffffff
        left_part = '%s.%d.%d' % (strftime('%Y%m%d%H%M%S'),
                                  os.getpid(),
                                  randrange(0, randmax))
        return "%s@%s" % (left_part, gethostname())

    def send(self, fromaddr, toaddrs, message):
        parser = rfc822.Message(StringIO(message))
        messageid = parser.getheader('Message-Id')
        if messageid:
            if not messageid.startswith('<') or not messageid.endswith('>'):
                raise ValueError('Malformed Message-Id header')
            messageid = messageid[1:-1]
        else:
            messageid = self.newMessageId()
            message = 'Message-Id: <%s>\n%s' % (messageid, message)
        transaction.get().join(
            self.createDataManager(fromaddr, toaddrs, message))
        return messageid


class DirectMailDelivery(AbstractMailDelivery):
    __doc__ = IDirectMailDelivery.__doc__

    implements(IDirectMailDelivery)

    def __init__(self, mailer):
        self.mailer = mailer

    def createDataManager(self, fromaddr, toaddrs, message):
        return MailDataManager(self.mailer.send,
                               args=(fromaddr, toaddrs, message))


class QueuedMailDelivery(AbstractMailDelivery):
    __doc__ = IQueuedMailDelivery.__doc__

    implements(IQueuedMailDelivery)

    def __init__(self, queuePath):
        self._queuePath = queuePath

    queuePath = property(lambda self: self._queuePath)

    def createDataManager(self, fromaddr, toaddrs, message):
        maildir = Maildir(self.queuePath, True)
        msg = maildir.newMessage()
        msg.write('X-Zope-From: %s\n' % fromaddr)
        msg.write('X-Zope-To: %s\n' % ", ".join(toaddrs))
        msg.write(message)
        msg.close()
        return MailDataManager(msg.commit, onAbort=msg.abort)


# The below diagram depicts the operations performed while sending a message in
# the ``run`` method of ``QueueProcessorThread``.  This sequence of operations
# will be performed for each file in the maildir each time the thread "wakes
# up" to send messages.
#
# Any error conditions not depected on the diagram will provoke the catch-all
# exception logging of the ``run`` method.
#
# In the diagram the "message file" is the file in the maildir's "cur" directory
# that contains the message and "tmp file" is a hard link to the message file
# created in the maildir's "tmp" directory.
#
#           ( start trying to deliver a message )
#                            |
#                            |
#                            V
#            +-----( get tmp file mtime )
#            |               |
#            |               | file exists
#            |               V
#            |         ( check age )-----------------------------+
#   tmp file |               |                       file is new |
#   does not |               | file is old                       |
#   exist    |               |                                   |
#            |      ( unlink tmp file )-----------------------+  |
#            |               |                      file does |  |
#            |               | file unlinked        not exist |  |
#            |               V                                |  |
#            +---->( touch message file )------------------+  |  |
#                            |                   file does |  |  |
#                            |                   not exist |  |  |
#                            V                             |  |  |
#            ( link message file to tmp file )----------+  |  |  |
#                            |                 tmp file |  |  |  |
#                            |           already exists |  |  |  |
#                            |                          |  |  |  |
#                            V                          V  V  V  V
#                     ( send message )             ( skip this message )
#                            |
#                            V
#                 ( unlink message file )---------+
#                            |                    |
#                            | file unlinked      | file no longer exists
#                            |                    |
#                            |  +-----------------+
#                            |  |
#                            |  V
#                  ( unlink tmp file )------------+
#                            |                    |
#                            | file unlinked      | file no longer exists
#                            V                    |
#                  ( message delivered )<---------+

class QueueProcessorThread(threading.Thread):
    """This thread is started at configuration time from the
    `mail:queuedDelivery` directive handler.
    """

    log = logging.getLogger("QueueProcessorThread")
    __stopped = False

    def __init__(self, interval=3.0):
        threading.Thread.__init__(self)
        self.interval = interval

    def setMaildir(self, maildir):
        """Set the maildir.

        This method is used just to provide a `maildir` stubs ."""
        self.maildir = maildir

    def setQueuePath(self, path):
        self.maildir = Maildir(path, True)

    def setMailer(self, mailer):
        self.mailer = mailer

    def _parseMessage(self, message):
        """Extract fromaddr and toaddrs from the first two lines of
        the `message`.

        Returns a fromaddr string, a toaddrs tuple and the message
        string.
        """

        fromaddr = ""
        toaddrs = ()
        rest = ""

        try:
            first, second, rest = message.split('\n', 2)
        except ValueError:
            return fromaddr, toaddrs, message

        if first.startswith("X-Zope-From: "):
            i = len("X-Zope-From: ")
            fromaddr = first[i:]

        if second.startswith("X-Zope-To: "):
            i = len("X-Zope-To: ")
            toaddrs = tuple(second[i:].split(", "))

        return fromaddr, toaddrs, rest

    def run(self, forever=True):
        atexit.register(self.stop)
        while not self.__stopped:
            for filename in self.maildir:
                # if we are asked to stop while sending messages, do so
                if self.__stopped:
                    break

                fromaddr = ''
                toaddrs = ()
                head, tail = os.path.split(filename)
                tmp_filename = os.path.join(head, '.sending-' + tail)
                rejected_filename = os.path.join(head, '.rejected-' + tail)
                try:
                    # perform a series of operations in an attempt to ensure
                    # that no two threads/processes send this message
                    # simultaneously as well as attempting to not generate
                    # spurious failure messages in the log; a diagram that
                    # represents these operations is included in a
                    # comment above this class
                    try:
                        # find the age of the tmp file (if it exists)
                        age = None
                        mtime = os.stat(tmp_filename)[stat.ST_MTIME]
                        age = time.time() - mtime
                    except OSError, e:
                        if e.errno == 2: # file does not exist
                            # the tmp file could not be stated because it
                            # doesn't exist, that's fine, keep going
                            pass
                        else:
                            # the tmp file could not be stated for some reason
                            # other than not existing; we'll report the error
                            raise

                    # if the tmp file exists, check it's age
                    if age is not None:
                        try:
                            if age > MAX_SEND_TIME:
                                # the tmp file is "too old"; this suggests
                                # that during an attemt to send it, the
                                # process died; remove the tmp file so we
                                # can try again
                                os.unlink(tmp_filename)
                            else:
                                # the tmp file is "new", so someone else may
                                # be sending this message, try again later
                                continue
                            # if we get here, the file existed, but was too
                            # old, so it was unlinked
                        except OSError, e:
                            if e.errno == 2: # file does not exist
                                # it looks like someone else removed the tmp
                                # file, that's fine, we'll try to deliver the
                                # message again later
                                continue

                    # now we know that the tmp file doesn't exist, we need to
                    # "touch" the message before we create the tmp file so the
                    # mtime will reflect the fact that the file is being
                    # processed (there is a race here, but it's OK for two or
                    # more processes to touch the file "simultaneously")
                    try:
                        os.utime(filename, None)
                    except OSError, e:
                        if e.errno == 2: # file does not exist
                            # someone removed the message before we could
                            # touch it, no need to complain, we'll just keep
                            # going
                            continue

                    # creating this hard link will fail if another process is
                    # also sending this message
                    try:
                        _os_link(filename, tmp_filename)
                    except OSError, e:
                        if e.errno == 17: # file exists, *nix
                            # it looks like someone else is sending this
                            # message too; we'll try again later
                            continue
                        
                    # FIXME: Need to test in Windows.  If 
                    # test_concurrent_delivery passes, this stanza can be
                    # deleted.  Otherwise we probably need to catch 
                    # WindowsError and check for corresponding error code.
                    #except error, e:
                    #    if e[0] == 183 and e[1] == 'CreateHardLink':
                    #        # file exists, win32
                    #        continue

                    # read message file and send contents
                    file = open(filename)
                    message = file.read()
                    file.close()
                    fromaddr, toaddrs, message = self._parseMessage(message)
                    try:
                        self.mailer.send(fromaddr, toaddrs, message)
                    except smtplib.SMTPResponseException, e:
                        if 500 <= e.smtp_code <= 599:
                            # permanent error, ditch the message
                            self.log.error(
                                "Discarding email from %s to %s due to"
                                " a permanent error: %s",
                                fromaddr, ", ".join(toaddrs), str(e))
                            #os.link(filename, rejected_filename)
                            _os_link(filename, rejected_filename)
                        else:
                            # Log an error and retry later
                            raise

                    try:
                        os.unlink(filename)
                    except OSError, e:
                        if e.errno == 2: # file does not exist
                            # someone else unlinked the file; oh well
                            pass
                        else:
                            # something bad happend, log it
                            raise

                    try:
                        os.unlink(tmp_filename)
                    except OSError, e:
                        if e.errno == 2: # file does not exist
                            # someone else unlinked the file; oh well
                            pass
                        else:
                            # something bad happend, log it
                            raise

                    # TODO: maybe log the Message-Id of the message sent
                    self.log.info("Mail from %s to %s sent.",
                                  fromaddr, ", ".join(toaddrs))
                    # Blanket except because we don't want
                    # this thread to ever die
                except:
                    if fromaddr != '' or toaddrs != ():
                        self.log.error(
                            "Error while sending mail from %s to %s.",
                            fromaddr, ", ".join(toaddrs), exc_info=True)
                    else:
                        self.log.error(
                            "Error while sending mail : %s ",
                            filename, exc_info=True)
            else:
                if forever:
                    time.sleep(self.interval)

            # A testing plug
            if not forever:
                break

    def stop(self):
        self.__stopped = True
