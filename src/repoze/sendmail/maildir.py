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
"""Read/write access to `Maildir` folders.

$Id: maildir.py 76463 2007-06-07 13:24:21Z mgedmin $
"""
__docformat__ = 'restructuredtext'

import os
import errno
import socket
import time
import random

from zope.interface import implements, classProvides

from repoze.sendmail.interfaces import \
     IMaildirFactory, IMaildir, IMaildirMessageWriter


class Maildir(object):
    """See `repoze.sendmail.interfaces.IMaildir`"""

    classProvides(IMaildirFactory)
    implements(IMaildir)

    def __init__(self, path, create=False):
        "See `repoze.sendmail.interfaces.IMaildirFactory`"
        self.path = path

        def access(path):
            return os.access(path, os.F_OK)

        subdir_cur = os.path.join(path, 'cur')
        subdir_new = os.path.join(path, 'new')
        subdir_tmp = os.path.join(path, 'tmp')

        if create and not access(path):
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

    def newMessage(self):
        "See `repoze.sendmail.interfaces.IMaildir`"
        # NOTE: http://www.qmail.org/man/man5/maildir.html says, that the first
        #       step of the delivery process should be a chdir.  Chdirs and
        #       threading do not mix.  Is that chdir really necessary?
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
                fd = os.open(filename, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0600)
            except OSError, e:
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
        return MaildirMessageWriter(os.fdopen(fd, 'w'), filename,
                                    join(subdir_new, unique))


def _encode_utf8(s):
    if isinstance(s, unicode):
        s = s.encode('utf-8')
    return s

class MaildirMessageWriter(object):
    """See `repoze.sendmail.interfaces.IMaildirMessageWriter`"""

    implements(IMaildirMessageWriter)

    def __init__(self, fd, filename, new_filename):
        self._filename = filename
        self._new_filename = new_filename
        self._fd = fd
        self._finished = False
        self._aborted = False

    def write(self, data):
        self._fd.write(_encode_utf8(data))

    def writelines(self, lines):
        lines = map(_encode_utf8, lines)
        self._fd.writelines(lines)

    def close(self):
        self._fd.close()

    def commit(self):
        if self._aborted:
            raise RuntimeError('Cannot commit, message already aborted')
        elif not self._finished:
            self._finished = True
            self._fd.close()
            os.rename(self._filename, self._new_filename)
            # NOTE: the same maildir.html says it should be a link, followed by
            #       unlink.  But Win32 does not necessarily have hardlinks!

    def abort(self):
        # XXX mgedmin: I think it is dangerous to have an abort() that does
        # nothing when commit() already succeeded.  But the tests currently
        # test that expectation.
        if not self._finished:
            self._finished = True
            self._aborted = True
            self._fd.close()
            os.unlink(self._filename)

    # XXX: should there be a __del__ that calls abort()?

