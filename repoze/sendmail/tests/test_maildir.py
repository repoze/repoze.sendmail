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

import unittest


class TestMaildir(unittest.TestCase):

    def setUp(self):
        import repoze.sendmail.maildir as maildir_module
        self.maildir_module = maildir_module
        self.old_os_module = maildir_module.os
        self.old_time_module = maildir_module.time
        self.old_socket_module = maildir_module.socket
        maildir_module.os = self.fake_os_module = FakeOsModule()
        maildir_module.time = FakeTimeModule()
        maildir_module.socket = FakeSocketModule()

    def tearDown(self):
        self.maildir_module.os = self.old_os_module
        self.maildir_module.time = self.old_time_module
        self.maildir_module.socket = self.old_socket_module
        self.fake_os_module._stat_never_fails = False
        self.fake_os_module._all_files_exist = False

    def test_factory(self):
        from repoze.sendmail.maildir import Maildir

        # Case 1: normal maildir
        Maildir('/path/to/maildir')

        # Case 2a: directory does not exist, create = False
        self.assertRaises(ValueError, Maildir, '/path/to/nosuchfolder', False)

        # Case 2b: directory does not exist, create = True
        Maildir('/path/to/nosuchfolder', True)
        dirs = list(self.fake_os_module._made_directories)
        dirs.sort()
        self.assertEqual(dirs, ['/path/to/nosuchfolder',
                                '/path/to/nosuchfolder/cur',
                                '/path/to/nosuchfolder/new',
                                '/path/to/nosuchfolder/tmp'])

        # Case 3: it is a file, not a directory
        self.assertRaises(ValueError, Maildir, '/path/to/regularfile', False)
        self.assertRaises(ValueError, Maildir, '/path/to/regularfile', True)

        # Case 4: it is a directory, but not a maildir
        self.assertRaises(ValueError, Maildir, '/path/to/emptydirectory', False)
        self.assertRaises(ValueError, Maildir, '/path/to/emptydirectory', True)

    def test_iteration(self):
        from repoze.sendmail.maildir import Maildir
        m = Maildir('/path/to/maildir')
        messages = list(m)
        self.assertEqual(messages, ['/path/to/maildir/new/1', 
                                    '/path/to/maildir/new/2',
                                    '/path/to/maildir/cur/2',
                                    '/path/to/maildir/cur/1'])

    def test_add(self):
        from email.message import Message
        from repoze.sendmail.maildir import Maildir
        m = Maildir('/path/to/maildir')
        tx_message = m.add(Message())
        self.assertTrue(tx_message._pending_path,
                     '/path/to/maildir/tmp/1234500002.4242.myhostname.')

    def test_add_no_good_filenames(self):
        from email.message import Message
        from repoze.sendmail.maildir import Maildir
        self.fake_os_module._all_files_exist = True
        m = Maildir('/path/to/maildir')
        self.assertRaises(RuntimeError, m.add, Message())

    def test_add_os_error(self):
        from email.message import Message
        from repoze.sendmail.maildir import Maildir
        self.fake_os_module._exception = OSError('test')
        m = Maildir('/path/to/maildir')
        self.assertRaises(OSError, m.add, Message())

    def test_tx_msg_abort(self):
        from repoze.sendmail.maildir import MaildirTransactionalMessage
        filename1 = '/path/to/maildir/tmp/1234500002.4242.myhostname'
        filename2 = '/path/to/maildir/new/1234500002.4242.myhostname'
        tx_msg = MaildirTransactionalMessage(filename1, filename2)
        self.assertEqual(tx_msg._pending_path, filename1)

        tx_msg.abort()
        self.assertEqual(tx_msg._aborted, True)
        self.assertEqual(tx_msg._committed, False)
        self.assertTrue(filename1 in self.fake_os_module._removed_files)

        tx_msg.abort()
        self.assertRaises(RuntimeError, tx_msg.commit)

    def test_tx_msg_commit(self):
        from repoze.sendmail.maildir import MaildirTransactionalMessage
        filename1 = '/path/to/maildir/tmp/1234500002.4242.myhostname'
        filename2 = '/path/to/maildir/new/1234500002.4242.myhostname'
        tx_msg = MaildirTransactionalMessage(filename1, filename2)
        self.assertEqual(tx_msg._pending_path, filename1)

        tx_msg.commit()
        self.assertEqual(tx_msg._aborted, False)
        self.assertEqual(tx_msg._committed, True)
        self.assertTrue((filename1, filename2)
                       in self.fake_os_module._renamed_files)

        self.assertRaises(RuntimeError, tx_msg.abort)
        self.assertRaises(RuntimeError, tx_msg.commit)

    def test_mx_msg_delete(self):
        from repoze.sendmail.maildir import MaildirTransactionalMessage
        filename1 = '/path/to/maildir/tmp/1234500002.4242.myhostname'
        filename2 = '/path/to/maildir/new/1234500002.4242.myhostname'
        self.fake_os_module.path.files[filename1] = 1
        tx_msg = MaildirTransactionalMessage(filename1, filename2)
        tx_msg.debug = True
        tx_msg.__del__()
        self.assertEqual(self.fake_os_module._removed_files, (filename1,))


class FakeSocketModule(object):

    def gethostname(self):
        return 'myhostname'

class FakeTimeModule(object):

    _timer = 1234500000

    def time(self):
        return self._timer

    def sleep(self, n):
        self._timer += n

class FakeOsPathModule(object):

    def __init__(self, files, dirs):
        self.files = dict(files)
        self.dirs = dict(dirs)
        mtimes = {}
        for t,f in enumerate(files):
            mtimes[f] = 9999 - t
        self._mtimes = mtimes

    def join(self, *args):
        return '/'.join(args)

    def isdir(self, dir):
        return dir in self.dirs

    def getmtime(self, f):
        return self._mtimes.get(f, 10000)

    def exists(self, path):
        return path in self.dirs or path in self.files

def _stat_files():
    import stat
    return [
        ('/path/to/maildir', stat.S_IFDIR),
        ('/path/to/maildir/new', stat.S_IFDIR),
        ('/path/to/maildir/new/1', stat.S_IFREG),
        ('/path/to/maildir/new/2', stat.S_IFREG),
        ('/path/to/maildir/cur', stat.S_IFDIR),
        ('/path/to/maildir/cur/1', stat.S_IFREG),
        ('/path/to/maildir/cur/2', stat.S_IFREG),
        ('/path/to/maildir/tmp', stat.S_IFDIR),
        ('/path/to/maildir/tmp/1', stat.S_IFREG),
        ('/path/to/maildir/tmp/2', stat.S_IFREG),
        ('/path/to/maildir/tmp/1234500000.4242.myhostname.*', stat.S_IFREG),
        ('/path/to/maildir/tmp/1234500001.4242.myhostname.*', stat.S_IFREG),
        ('/path/to/regularfile', stat.S_IFREG),
        ('/path/to/emptydirectory', stat.S_IFDIR),
    ]

def _listdir_files():
    return [
        ('/path/to/maildir/new', ['1', '2', '.svn']),
        ('/path/to/maildir/cur', ['2', '1', '.tmp']),
        ('/path/to/maildir/tmp', ['1', '2', '.ignore']),
    ]

class FakeOsModule(object):

    F_OK = 0

    path = FakeOsPathModule(_stat_files(), _listdir_files())

    _made_directories = ()
    _removed_files = ()
    _renamed_files = ()

    _all_files_exist = False
    _exception = None

    def __init__(self):
        import os
        self._descriptors = {}
        self.O_CREAT = os.O_CREAT
        self.O_EXCL = os.O_EXCL
        self.O_WRONLY = os.O_WRONLY
        self.O_RDWR = os.O_RDWR

    def access(self, path, mode):
        modes = dict(_stat_files())
        if self._all_files_exist:
            return True
        if path in modes:
            return True
        if path.rsplit('.', 1)[0] + '.*' in modes:
            return True
        return False

    def listdir(self, path):
        listdir = dict(_listdir_files())
        return listdir.get(path, [])

    def mkdir(self, path):
        self._made_directories += (path, )

    def getpid(self):
        return 4242

    def remove(self, path):
        self._removed_files += (path, )

    def rename(self, old, new):
        self._renamed_files += ((old, new), )

    def open(self, filename, flags,
             mode=511  # BBB Python 2 vs 3, 0o777 in octal
             ):
        import errno
        if self._exception is not None:
            raise self._exception
        if (flags & self.O_EXCL and flags & self.O_CREAT
            and self.access(filename, 0)):
            raise OSError(errno.EEXIST, 'file already exists')
        if not flags & self.O_CREAT and not self.access(filename, 0):
            raise OSError('file not found') #pragma NO COVERAGE defensive
        fd = max(list(self._descriptors.keys()) + [2]) + 1
        self._descriptors[fd] = filename, flags, mode
        return fd

    def fdopen(self, fd, mode='r'):
        filename, flags, permissions = self._descriptors[fd]
        if mode == 'w':
            assert flags & self.O_WRONLY
            assert not flags & self.O_RDWR
        else: #pragma NO COVERAGE defensive programming
            raise AssertionError("don't know how to verify if flags match"
                                 " mode %r" % mode)
        return FakeFile(filename, mode)


class FakeFile(object):

    def __init__(self, filename, mode):
        self._filename = filename
        self._mode = mode
        self._written = ''
        self._closed = False

    def close(self):
        self._closed = True

    def write(self, data):
        self._written += data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
