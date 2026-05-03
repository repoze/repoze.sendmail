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
"""
Read/write access to `Maildir` folders.
"""

import contextlib
import os
import pathlib
import random
import socket
import time
from email import generator as email_generator

HOSTNAME = None
PID = None
RANDMAX = 0x7FFFFFFF


class NotAMaildir(ValueError):
    def __init__(self, path):
        self.path = path
        super().__init__(f"{path} is not a Maildir folder")


class NoTempfileNamesAvailable(RuntimeError):
    def __init__(self, subdir_tmp):
        self.subdir_tmp = subdir_tmp
        super().__init__(
            f"Failed to create unique file name in {subdir_tmp}, "
            f"are we under a DoS attack?"
        )


class TransactionAborted(RuntimeError):
    def __init__(self):
        super().__init__("Cannot commit--already aborted.")


class TransactionCommitted(RuntimeError):
    def __init__(self):
        super().__init__("Cannot commit--already  committed.")


def _check_maildir(path, create):
    path = pathlib.Path(path)

    subdir_cur = path / "cur"
    subdir_new = path / "new"
    subdir_tmp = path / "tmp"

    if create and not path.exists():
        path.mkdir()
        subdir_cur.mkdir()
        subdir_new.mkdir()
        subdir_tmp.mkdir()
        is_maildir = True
    else:
        is_maildir = (
            subdir_cur.exists() and subdir_new.exists() and subdir_tmp.exists()
        )

    return path, is_maildir


def _unique_filename():
    global HOSTNAME
    global PID

    if HOSTNAME is None:
        HOSTNAME = socket.gethostname()

    if PID is None:
        PID = os.getpid()

    timestamp = time.time()
    randint = random.randrange(RANDMAX)

    return f"{timestamp}.{PID}.{HOSTNAME}.{randint}"


def _open_unique_filename(subdir_tmp, max_count=1000, sleep_interval=0.1):
    # Return 'fd' from open, on success, plus the 'unique' path suffix
    counter = 0
    while counter < max_count:
        unique = _unique_filename()
        filename = subdir_tmp / unique
        try:
            if 1:  # use pathlib.Path, retrn stream
                return filename.open("x"), unique
            else:  # pragma NO COVER use 'os.open', return fd
                return (
                    os.open(
                        filename, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
                    ),
                    unique,
                )
        except FileExistsError:
            # NOTE: maildir.html (see above) says I should sleep for 2
            counter += 1
            time.sleep(sleep_interval)

    raise NoTempfileNamesAvailable(subdir_tmp)


class Maildir:
    """See `repoze.sendmail.interfaces.IMaildir`"""

    def __init__(self, path, create=False):
        """See `repoze.sendmail.interfaces.IMaildirFactory`"""
        path, is_maildir = _check_maildir(path, create=create)

        if not is_maildir:
            raise NotAMaildir(path)

        self.path = path

    @property
    def subdir_cur(self):
        return self.path / "cur"

    @property
    def subdir_new(self):
        return self.path / "new"

    @property
    def subdir_tmp(self):
        return self.path / "tmp"

    def __iter__(self):
        "See `repoze.sendmail.interfaces.IMaildir`"
        # http://www.qmail.org/man/man5/maildir.html says:
        #     "It is a good idea for readers to skip all filenames in new
        #     and cur starting with a dot.  Other than this, readers
        #     should not attempt to parse filenames."
        new_messages = list(self.subdir_new.glob("*"))
        cur_messages = list(self.subdir_cur.glob("*"))

        # Sort by modification time so earlier messages are sent before
        # later messages during queue processing.
        msgs_sorted = [
            (str(m), m.stat().st_mtime) for m in new_messages + cur_messages
        ]
        msgs_sorted.sort(key=lambda x: x[1])
        return iter([m[0] for m in msgs_sorted])

    def add(self, message):
        "See `repoze.sendmail.interfaces.IMaildir`"

        if 1:  # use pathlib, receive stream
            stream, unique = _open_unique_filename(self.subdir_tmp)

            with contextlib.closing(stream) as f:
                writer = email_generator.Generator(f)
                writer.flatten(message)

        else:  # pragma NO COVER use os.open, receive fd
            fd, unique = _open_unique_filename(self.subdir_tmp)
            with os.fdopen(fd, "w") as f:
                writer = email_generator.Generator(f)
                writer.flatten(message)

        return MaildirTransactionalMessage(
            self.subdir_tmp / unique,
            self.subdir_new / unique,
        )


class MaildirTransactionalMessage:
    """See `repoze.sendmail.interfaces.ITransactionalMessage`"""

    def __init__(self, pending_path, committed_path):
        self._pending_path = pending_path
        self._committed_path = committed_path
        self._committed = False
        self._aborted = False

    def commit(self):
        if self._aborted:
            raise TransactionAborted()
        if self._committed:
            raise TransactionCommitted()

        os.rename(self._pending_path, self._committed_path)
        self._committed = True

    def abort(self):
        if self._aborted:
            return
        if self._committed:
            raise TransactionCommitted()

        self._aborted = True
        os.remove(self._pending_path)

    def __del__(self):
        if (
            not self._aborted
            and not self._committed
            and os.path.exists(self._pending_path)
        ):
            os.remove(self._pending_path)
