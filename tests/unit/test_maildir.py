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
import time
from email import message as email_message
from unittest import mock

import pytest

import repoze.sendmail.maildir as maildir_module

TEST_HOSTNAME = "test.example.com"
TEST_PID = 123456
TEST_RANDINT = 47
TEST_TIMESTAMP = time.time()


@pytest.fixture
def valid_maildir(tmp_path):
    for sub in ["cur", "new", "tmp"]:
        (tmp_path / sub).mkdir()

    return tmp_path


@pytest.fixture
def populated_maildir(valid_maildir):
    (valid_maildir / "new" / "1").write_text("new #1")
    (valid_maildir / "new" / "2").write_text("new #2")
    (valid_maildir / "cur" / "2").write_text("current #2")
    (valid_maildir / "cur" / "1").write_text("current #1")
    (valid_maildir / "tmp" / "1234500000.4242.myhostname.*").write_text(
        "temp #1234500000"
    )
    (valid_maildir / "tmp" / "1234500001.4242.myhostname.*").write_text(
        "temp #1234500001"
    )
    return valid_maildir


@pytest.fixture
def hostname_pid_not_set():
    with mock.patch.multiple(
        "repoze.sendmail.maildir",
        HOSTNAME=None,
        PID=None,
    ):
        yield


def test__check_maildir_w_already(valid_maildir):
    path, is_maildir = maildir_module._check_maildir(
        valid_maildir,
        create=False,
    )

    assert is_maildir
    assert path == valid_maildir


def test__check_maildir_w_empty_wo_create(tmp_path):
    found, is_maildir = maildir_module._check_maildir(tmp_path, create=False)

    assert not is_maildir
    assert found == tmp_path


def test__check_maildir_w_empty_w_create(tmp_path):
    exp_path = tmp_path / "maildir"

    path, is_maildir = maildir_module._check_maildir(exp_path, create=True)

    assert is_maildir
    assert path == exp_path
    assert (exp_path / "cur").is_dir()
    assert (exp_path / "new").is_dir()
    assert (exp_path / "tmp").is_dir()


@pytest.mark.parametrize("w_create", [True, False])
def test__check_maildir_w_file(tmp_path, w_create):
    exp_path = tmp_path / "maildir"
    exp_path.write_text("I am not a maildir")

    found, is_maildir = maildir_module._check_maildir(
        exp_path,
        create=w_create,
    )

    assert not is_maildir
    assert found == exp_path


@mock.patch("socket.gethostname")
@mock.patch("os.getpid")
@mock.patch("random.randrange")
@mock.patch("time.time")
def test__unique_hostname_w_globals_not_set(
    tt,
    rrr,
    ogp,
    sgh,
    hostname_pid_not_set,
):
    tt.return_value = TEST_TIMESTAMP
    rrr.return_value = TEST_RANDINT
    ogp.return_value = TEST_PID
    sgh.return_value = TEST_HOSTNAME

    found = maildir_module._unique_filename()

    assert found == (
        f"{TEST_TIMESTAMP}.{TEST_PID}.{TEST_HOSTNAME}.{TEST_RANDINT}"
    )


@mock.patch("random.randrange")
@mock.patch("time.time")
def test__unique_hostname_w_globals_set(tt, rrr):
    tt.return_value = TEST_TIMESTAMP
    rrr.return_value = TEST_RANDINT

    with mock.patch.multiple(
        "repoze.sendmail.maildir",
        HOSTNAME=TEST_HOSTNAME,
        PID=TEST_PID,
    ):
        found = maildir_module._unique_filename()

    assert found == (
        f"{TEST_TIMESTAMP}.{TEST_PID}.{TEST_HOSTNAME}.{TEST_RANDINT}"
    )


@mock.patch("pathlib.Path.open")
@mock.patch("repoze.sendmail.maildir._unique_filename")
def test__open_unique_filename_w_oserror(ufn, ppo, tmp_path):
    ppo.side_effect = PermissionError("test")
    ufn.return_value = "not-allowed"

    with pytest.raises(PermissionError):
        maildir_module._open_unique_filename(tmp_path, max_count=2)


@mock.patch("repoze.sendmail.maildir._unique_filename")
def test__open_unique_filename_w_names_taken(ufn, tmp_path):
    ufn.return_value = "taken"
    taken = tmp_path / "taken"
    taken.write_text("TAKEN")

    with pytest.raises(maildir_module.NoTempfileNamesAvailable):
        maildir_module._open_unique_filename(tmp_path, max_count=2)


@mock.patch("repoze.sendmail.maildir._unique_filename")
def test__open_unique_filename_w_ok(ufn, tmp_path):
    ufn.return_value = "not-taken"
    not_taken = tmp_path / "not-taken"
    assert not not_taken.is_file()

    stream, unique = maildir_module._open_unique_filename(tmp_path)

    print("now-taken", file=stream, end="", flush=True)

    assert not_taken.read_text() == "now-taken"


@mock.patch("repoze.sendmail.maildir._check_maildir")
def test_maildir_ctor_w_hit(chkmd, tmp_path):
    chkmd.return_value = tmp_path, True

    found = maildir_module.Maildir(tmp_path)

    assert found.path == tmp_path
    chkmd.assert_called_once_with(tmp_path, create=False)

    assert found.subdir_cur == tmp_path / "cur"
    assert found.subdir_new == tmp_path / "new"
    assert found.subdir_tmp == tmp_path / "tmp"


@mock.patch("repoze.sendmail.maildir._check_maildir")
def test_maildir_ctor_w_miss(chkmd, tmp_path):
    chkmd.return_value = tmp_path, False

    with pytest.raises(maildir_module.NotAMaildir):
        maildir_module.Maildir(tmp_path, create=False)

    chkmd.assert_called_once_with(tmp_path, create=False)


@mock.patch("repoze.sendmail.maildir._check_maildir")
def test_maildir_ctor_w_empty_w_create(chkmd, tmp_path):
    exp_path = tmp_path / "maildir"
    chkmd.return_value = exp_path, True

    found = maildir_module.Maildir(exp_path, create=True)

    assert found.path == exp_path
    chkmd.assert_called_once_with(exp_path, create=True)


def test_maildir___iter___w_empty(valid_maildir):
    maildir = maildir_module.Maildir(valid_maildir)

    found = list(maildir)

    assert found == []


def test_maildir___iter___w_populated(populated_maildir):
    maildir = maildir_module.Maildir(populated_maildir)
    expected_paths = [
        populated_maildir / sub / name
        for sub, name in [
            ("new", "1"),
            ("new", "2"),
            ("cur", "2"),
            ("cur", "1"),
        ]
    ]

    found = list(maildir)

    assert found == [str(exp) for exp in expected_paths]


@mock.patch("repoze.sendmail.maildir._unique_filename")
def test_maildir_add_ok(
    ufn,
    valid_maildir,
):
    ufn.return_value = "unique"
    exp_filename = valid_maildir / "tmp" / "unique"
    maildir = maildir_module.Maildir(valid_maildir)
    msg = email_message.Message()
    msg.add_header("x-testing", "this is a test")

    tx_message = maildir.add(msg)

    assert tx_message._pending_path == exp_filename
    assert tx_message._committed_path == (valid_maildir / "new" / "unique")
    assert exp_filename.is_file()
    assert "this is a test" in exp_filename.read_text()


def test_mdtxmsg_abort(valid_maildir):
    pending = valid_maildir / "tmp" / "1234500002.4242.myhostname"
    pending.touch()
    committed = valid_maildir / "new" / "1234500002.4242.myhostname"

    tx_msg = maildir_module.MaildirTransactionalMessage(pending, committed)

    assert tx_msg._pending_path == pending
    assert pending.exists()

    assert tx_msg._committed_path == committed
    assert not committed.exists()

    tx_msg.abort()

    assert tx_msg._aborted
    assert not tx_msg._committed

    assert not pending.exists()

    tx_msg.abort()  # no-op if aborted

    with pytest.raises(maildir_module.TransactionAborted):
        tx_msg.commit()


def test_mdtxmsg_commit(valid_maildir):
    pending = valid_maildir / "tmp" / "1234500002.4242.myhostname"
    pending.write_text("commit me")
    committed = valid_maildir / "new" / "1234500002.4242.myhostname"
    tx_msg = maildir_module.MaildirTransactionalMessage(pending, committed)

    assert pending.is_file()
    assert not committed.exists()

    tx_msg.commit()

    assert not tx_msg._aborted
    assert tx_msg._committed

    assert not pending.exists()
    assert committed.read_text() == "commit me"

    with pytest.raises(maildir_module.TransactionCommitted):
        tx_msg.abort()

    with pytest.raises(maildir_module.TransactionCommitted):
        tx_msg.commit()


def test_mdtxmsg_delete(valid_maildir):
    pending = valid_maildir / "tmp" / "1234500002.4242.myhostname"
    pending.write_text("commit me")
    committed = valid_maildir / "new" / "1234500002.4242.myhostname"
    tx_msg = maildir_module.MaildirTransactionalMessage(pending, committed)

    assert pending.is_file()
    assert not committed.exists()

    tx_msg.__del__()

    assert not pending.exists()
    assert not committed.exists()
