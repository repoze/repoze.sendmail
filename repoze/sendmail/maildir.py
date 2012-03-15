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
from __future__ import with_statement

"""
Read/write access to `Maildir` folders.
"""

import sys
import os
import errno
import socket
import time
import random
from email.generator import Generator

class Maildir(object):
    """See `repoze.sendmail.interfaces.IMaildir`"""

    def __init__(self, path, create=False):
        """See `repoze.sendmail.interfaces.IMaildirFactory`"""
        self.path = path

        subdir_cur = os.path.join(path, 'cur')
        subdir_new = os.path.join(path, 'new')
        subdir_tmp = os.path.join(path, 'tmp')

        if create and not os.access(path, os.F_OK):
            os.mkdir(path)
            os.mkdir(subdir_cur)
            os.mkdir(subdir_new)
            os.mkdir(subdir_tmp)
            maildir = True
        else:
            maildir = (os.path.isdir(subdir_cur) and os.path.isdir(subdir_new)
                       and os.path.isdir(subdir_tmp))
        if not maildir:
            raise ValueError('%s is not a Maildir folder' % path)

    def __iter__(self):
        "See `repoze.sendmail.interfaces.IMaildir`"
        join = os.path.join
        subdir_cur = join(self.path, 'cur')
        subdir_new = join(self.path, 'new')
        # http://www.qmail.org/man/man5/maildir.html says:
        #     "It is a good idea for readers to skip all filenames in new
        #     and cur starting with a dot.  Other than this, readers
        #     should not attempt to parse filenames."
        new_messages = [join(subdir_new, x) for x in os.listdir(subdir_new)
                        if not x.startswith('.')]
        cur_messages = [join(subdir_cur, x) for x in os.listdir(subdir_cur)
                        if not x.startswith('.')]

        # Sort by modification time so earlier messages are sent before
        # later messages during queue processing.
        msgs_sorted = [(m, os.path.getmtime(m)) for m
                      in new_messages + cur_messages]
        msgs_sorted.sort(key=lambda x: x[1])
        return iter([m[0] for m in msgs_sorted])

    def add(self, message):
        "See `repoze.sendmail.interfaces.IMaildir`"
        join = os.path.join
        subdir_tmp = join(self.path, 'tmp')
        subdir_new = join(self.path, 'new')
        pid = os.getpid()
        host = socket.gethostname()
        randmax = 0x7fffffff
        counter = 0
        while True:
            timestamp = int(time.time())
            unique = '%d.%d.%s.%d' % (timestamp, pid, host,
                                      random.randrange(randmax))
            filename = join(subdir_tmp, unique)
            try:
                fd = os.open(filename,
                             os.O_CREAT|os.O_EXCL|os.O_WRONLY,
                             384  # BBB Python 2 vs 3, 0o600 in octal
                             )
            except OSError:
                # BBB Python 2.5 compat
                e = sys.exc_info()[1]
                if e.errno != errno.EEXIST:
                    raise
                # File exists
                counter += 1
                if counter >= 1000:
                    raise RuntimeError("Failed to create unique file name"
                                       " in %s, are we under a DoS attack?"
                                       % subdir_tmp)
                # NOTE: maildir.html (see above) says I should sleep for 2
                time.sleep(0.1)
            else:
                break

        with os.fdopen(fd, 'w') as f:
            writer = Generator(f)
            writer.flatten(message)

        return MaildirTransactionalMessage(filename, join(subdir_new, unique))


class MaildirTransactionalMessage(object):
    """See `repoze.sendmail.interfaces.ITransactionalMessage`"""

    def __init__(self, pending_path, committed_path):
        self._pending_path = pending_path
        self._committed_path = committed_path
        self._committed = False
        self._aborted = False

    def commit(self):
        if self._aborted:
            raise RuntimeError('Cannot commit--already aborted.')
        if self._committed:
            raise RuntimeError('Cannot commit--already committed.')

        os.rename(self._pending_path, self._committed_path)
        self._committed = True

    def abort(self):
        if self._aborted:
            return
        if self._committed:
            raise RuntimeError('Cannot abort--already committed.')

        self._aborted = True
        os.remove(self._pending_path)

    def __del__(self):
        if (not self._aborted and
            not self._committed and
            os.path.exists(self._pending_path)):
            os.remove(self._pending_path)
