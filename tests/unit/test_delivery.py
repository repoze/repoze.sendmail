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
import email.message
import os
from email.mime import base
from unittest import mock

import pytest
import transaction
from transaction import interfaces as txn_interfaces
from zope.interface import implementer
from zope.interface import verify

from repoze.sendmail import delivery as delivery_module
from repoze.sendmail import interfaces
from repoze.sendmail import queue as queue_module


def _makeMDM(callable=object, args=(), onAbort=None, **kw):
    return delivery_module.MailDataManager(callable, args, onAbort, **kw)


def test_mdm_class_conforms_to_IDataManager():
    verify.verifyClass(
        txn_interfaces.IDataManager,
        delivery_module.MailDataManager,
    )


def test_mdm_instance_conforms_to_IDataManager():
    verify.verifyObject(txn_interfaces.IDataManager, _makeMDM())


def test_mdm_ctor():
    mdm = _makeMDM(object, (1, 2))
    assert mdm.callable is object
    assert mdm.args == (1, 2)


def test_mdm_join_transaction_implicit():
    with transaction.manager as txn:
        mdm = _makeMDM(object)
        mdm.join_transaction()
        assert txn._resources == [mdm]
        assert mdm.transaction is txn


def test_mdm_join_transaction_explicit():
    mdm = _makeMDM(object)
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    assert txn._resources == (mdm,)
    assert mdm.transaction is txn


def test_mdm_join_transaction_conflict():
    txn1 = DummyTransaction()
    txn2 = DummyTransaction()
    mdm = _makeMDM(object)
    # Assign the tm, but without actually joining
    mdm.transaction = txn1
    mdm.join_transaction(txn2)
    assert mdm.transaction is txn2


def test_mdm_join_transaction_w_new_txn_wo_in_old_txn_resources():
    mdm = _makeMDM(object)
    txn1 = DummyTransaction()
    txn2 = DummyTransaction()
    mdm.join_transaction(txn1)
    with pytest.raises(delivery_module.InAnotherTransaction):
        mdm.join_transaction(txn2)
    assert mdm.transaction is txn1


def test_mdm_join_transaction_duplicated():
    mdm = _makeMDM(object)
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    mdm.join_transaction(txn)
    assert txn._resources == (mdm,)
    assert mdm.transaction is txn


def test_mdm__finish_wo_transaction():
    mdm = _makeMDM(object)
    with pytest.raises(delivery_module.NotInATransaction):
        mdm._finish(2)


def test_mdm__finish_w_transaction():
    mdm = _makeMDM(object)
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    mdm._finish(2)
    assert mdm.state == 2
    assert mdm.tpc_phase == 0


def test_mdm_commit_wo_transaction():
    mdm = _makeMDM(object)
    txn = DummyTransaction()
    with pytest.raises(delivery_module.NotInATransaction):
        mdm.commit(txn)


def test_mdm_commit_w_foreign_transaction():
    mdm = _makeMDM(object)
    txn1 = DummyTransaction()
    mdm.join_transaction(txn1)
    txn2 = DummyTransaction()
    with pytest.raises(delivery_module.InAnotherTransaction):
        mdm.commit(txn2)


def test_mdm_commit_w_TPC():
    mdm = _makeMDM(object)
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    mdm.tpc_phase = 1
    mdm.commit(txn)  # no raise


def test_mdm_commit_w_same_transaction():
    mdm = _makeMDM(object)
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    mdm.commit(txn)  # no raise


def test_mdm_abort_wo_transaction():
    mdm = _makeMDM(object)
    txn = DummyTransaction()
    with pytest.raises(delivery_module.NotInATransaction):
        mdm.abort(txn)


def test_mdm_abort_w_foreign_transaction():
    mdm = _makeMDM(object)
    txn1 = DummyTransaction()
    mdm.join_transaction(txn1)
    txn2 = DummyTransaction()
    with pytest.raises(delivery_module.InAnotherTransaction):
        mdm.abort(txn2)


def test_mdm_abort_w_TPC():
    mdm = _makeMDM(object)
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    mdm.tpc_phase = 1
    with pytest.raises(delivery_module.TPC_InProgress):
        mdm.abort(txn)


def test_mdm_abort_w_same_transaction():
    mdm = _makeMDM(object)
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    mdm.abort(txn)  # no raise


def test_mdm_abort_w_onAbort():
    _called = []

    def _onAbort():
        _called.append(True)

    mdm = _makeMDM(object, onAbort=_onAbort)
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    mdm.abort(txn)  # no raise
    assert _called == [True]


def test_mdm_sortKey():
    mdm = _makeMDM()
    assert mdm.sortKey() == str(id(mdm))


def test_mdm_savepoint_wo_transaction():
    mdm = _makeMDM()
    with pytest.raises(delivery_module.NotInATransaction):
        mdm.savepoint()


def test_mdm_savepoint_w_transaction():
    mdm = _makeMDM()
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    sp = mdm.savepoint()
    assert isinstance(sp, delivery_module.MailDataSavepoint)


def test_mdm_tpc_begin_wo_transaction():
    mdm = _makeMDM()
    txn = DummyTransaction()
    with pytest.raises(delivery_module.NotInATransaction):
        mdm.tpc_begin(txn)


def test_mdm_tpc_begin_w_foreign_transaction():
    mdm = _makeMDM(object)
    txn1 = DummyTransaction()
    mdm.join_transaction(txn1)
    txn2 = DummyTransaction()
    with pytest.raises(delivery_module.InAnotherTransaction):
        mdm.tpc_begin(txn2)


def test_mdm_tpc_begin_already_tpc():
    mdm = _makeMDM()
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    mdm.tpc_phase = 1
    with pytest.raises(delivery_module.TPC_InProgress):
        mdm.tpc_begin(txn)


def test_mdm_tpc_begin_w_subtransaction():
    mdm = _makeMDM()
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    with pytest.raises(delivery_module.SubtransactionNotAllowed):
        mdm.tpc_begin(txn, True)


def test_mdm_tpc_begin_ok():
    mdm = _makeMDM()
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    mdm.tpc_begin(txn)
    assert mdm.tpc_phase == 1


def test_mdm_tpc_vote_wo_transaction():
    mdm = _makeMDM()
    txn = DummyTransaction()
    with pytest.raises(delivery_module.NotInATransaction):
        mdm.tpc_vote(txn)


def test_mdm_tpc_vote_w_foreign_transaction():
    mdm = _makeMDM(object)
    txn1 = DummyTransaction()
    mdm.join_transaction(txn1)
    txn2 = DummyTransaction()
    with pytest.raises(delivery_module.InAnotherTransaction):
        mdm.tpc_vote(txn2)


def test_mdm_tpc_vote_not_already_tpc():
    mdm = _makeMDM()
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    with pytest.raises(delivery_module.TPC_PhaseError):
        mdm.tpc_vote(txn)


def test_mdm_tpc_vote_ok():
    mdm = _makeMDM()
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    mdm.tpc_phase = 1
    mdm.tpc_vote(txn)
    assert mdm.tpc_phase == 2


def test_mdm_tpc_finish_wo_transaction():
    mdm = _makeMDM()
    txn = DummyTransaction()
    with pytest.raises(delivery_module.NotInATransaction):
        mdm.tpc_finish(txn)


def test_mdm_tpc_finish_w_foreign_transaction():
    mdm = _makeMDM(object)
    txn1 = DummyTransaction()
    mdm.join_transaction(txn1)
    txn2 = DummyTransaction()
    with pytest.raises(delivery_module.InAnotherTransaction):
        mdm.tpc_finish(txn2)


def test_mdm_tpc_finish_not_already_tpc():
    mdm = _makeMDM()
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    with pytest.raises(delivery_module.TPC_PhaseError):
        mdm.tpc_finish(txn)


def test_mdm_tpc_finish_not_voted():
    mdm = _makeMDM()
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    mdm.tpc_phase = 1
    with pytest.raises(delivery_module.TPC_PhaseError):
        mdm.tpc_finish(txn)


def test_mdm_tpc_finish_ok():
    _called = []

    def _callable(*args):
        _called.append(args)

    mdm = _makeMDM(_callable, (1, 2))
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    mdm.tpc_phase = 2
    mdm.tpc_finish(txn)
    assert _called == [(1, 2)]
    assert mdm.state == delivery_module.MailDataManagerState.TPC_FINISHED
    assert mdm.tpc_phase == 0


def test_mdm_tpc_abort_wo_transaction():
    mdm = _makeMDM()
    txn = DummyTransaction()
    with pytest.raises(delivery_module.NotInATransaction):
        mdm.tpc_abort(txn)


def test_mdm_tpc_abort_w_foreign_transaction():
    mdm = _makeMDM(object)
    txn1 = DummyTransaction()
    mdm.join_transaction(txn1)
    txn2 = DummyTransaction()
    with pytest.raises(delivery_module.InAnotherTransaction):
        mdm.tpc_abort(txn2)


def test_mdm_tpc_abort_not_already_tpc():
    mdm = _makeMDM()
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    with pytest.raises(delivery_module.TPC_PhaseError):
        mdm.tpc_abort(txn)


def test_mdm_tpc_abort_already_finished():
    mdm = _makeMDM()
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    mdm.tpc_phase = 1
    mdm.state = delivery_module.MailDataManagerState.TPC_FINISHED
    with pytest.raises(delivery_module.TPC_Finished):
        mdm.tpc_abort(txn)


def test_mdm_tpc_abort_begun_ok():
    mdm = _makeMDM()
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    mdm.tpc_phase = 1
    mdm.tpc_abort(txn)
    assert mdm.state == delivery_module.MailDataManagerState.TPC_ABORTED
    assert mdm.tpc_phase == 0


def test_mdm_tpc_abort_voted_ok():
    mdm = _makeMDM()
    txn = DummyTransaction()
    mdm.join_transaction(txn)
    mdm.tpc_phase = 2
    mdm.tpc_abort(txn)
    assert mdm.state == delivery_module.MailDataManagerState.TPC_ABORTED
    assert mdm.tpc_phase == 0


def _makeAMD():
    return delivery_module.AbstractMailDelivery()


def test_amd_send_w_bad_message():
    amd = _makeAMD()
    with pytest.raises(delivery_module.NotAnEmailMessage):
        amd.send("sender@example.com", ["recipient@example.com"], object())


def test_amd_send_w_bare_message():
    class DummyDM:
        joined = False
        extent = []

        def __init__(self, frm, to, msg):
            self.frm = frm
            self.to = to
            self.msg = msg
            self.extent.append(self)

        def join_transaction(self):
            self._joined = True

    amd = _makeAMD()
    amd.createDataManager = DummyDM
    msg = email.message.Message()
    amd.send("sender@example.com", ["recipient@example.com"], msg)
    assert "repoze.sendmail@" in msg["Message-Id"]
    assert "Date" in msg
    assert len(DummyDM.extent) == 1
    assert DummyDM.extent[0]._joined


def test_amd_send_w_populated_message():
    MESSAGE_ID = "12345@example.com"
    DATE = "Wed, 02 Oct 2002 08:00:00 EST"

    class DummyDM:
        joined = False
        extent = []

        def __init__(self, frm, to, msg):
            self.frm = frm
            self.to = to
            self.msg = msg
            self.extent.append(self)

        def join_transaction(self):
            self._joined = True

    amd = _makeAMD()
    amd.createDataManager = DummyDM
    msg = email.message.Message()
    msg["Message-Id"] = MESSAGE_ID
    msg["Date"] = DATE
    amd.send("sender@example.com", ["recipient@example.com"], msg)
    assert msg["Message-Id"] == MESSAGE_ID
    assert msg["Date"] == DATE
    assert len(DummyDM.extent) == 1
    assert DummyDM.extent[0]._joined


def _makeDMD(mailer=None, **kw):
    return delivery_module.DirectMailDelivery(mailer, **kw)


def test_dmd_class_conforms_to_IMailDelivery():
    verify.verifyClass(
        interfaces.IMailDelivery,
        delivery_module.DirectMailDelivery,
    )


def test_dmd_instance_conforms_to_IMailDelivery():
    verify.verifyObject(interfaces.IMailDelivery, _makeDMD())


def test_dmd_ctor():
    mailer = _makeMailerStub()
    delivery = _makeDMD(mailer)
    assert delivery.mailer == mailer


def test_dmd_ctor_w_tm():
    tm = object()
    mailer = _makeMailerStub()
    delivery = _makeDMD(mailer, transaction_manager=tm)
    assert delivery.mailer == mailer
    assert delivery.transaction_manager is tm


def test_dmd_send():
    mailer = _makeMailerStub()
    delivery = delivery_module.DirectMailDelivery(mailer)
    fromaddr = "Jim <jim@example.com"
    toaddrs = ("Guido <guido@example.com>", "Steve <steve@examplecom>")
    message = email.message.Message()
    message["From"] = "Jim <jim@example.org>"
    message["To"] = "some-zope-coders:;"
    message["Date"] = "Date: Mon, 19 May 2003 10:17:36 -0400"
    message["Message-Id"] = ext_msgid = "<20030519.1234@example.org>"
    message["Subject"] = "example"
    message.set_payload("This is just an example\n")

    msgid = delivery.send(fromaddr, toaddrs, message)
    assert msgid == "<20030519.1234@example.org>"
    assert mailer.sent_messages == []
    transaction.commit()
    assert mailer.sent_messages == [(fromaddr, toaddrs, message)]

    mailer.sent_messages = []
    msgid = delivery.send(fromaddr, toaddrs, message)
    assert "@" in msgid
    assert mailer.sent_messages == []
    transaction.commit()
    assert len(mailer.sent_messages) == 1
    assert mailer.sent_messages[0][0] == fromaddr
    assert mailer.sent_messages[0][1] == toaddrs
    assert (
        mailer.sent_messages[0][2].get_payload() == "This is just an example\n"
    )
    assert message["Message-Id"] == msgid
    assert message["Message-Id"] == ext_msgid

    mailer.sent_messages = []
    msgid = delivery.send(fromaddr, toaddrs, message)
    assert mailer.sent_messages == []
    transaction.abort()
    assert mailer.sent_messages == []


def test_dmd_send_returns_messageId():
    mailer = _makeMailerStub()
    delivery = delivery_module.DirectMailDelivery(mailer)
    fromaddr = "Jim <jim@example.com"
    toaddrs = ("Guido <guido@example.com>", "Steve <steve@examplecom>")
    message = email.message.Message()
    message["From"] = "Jim <jim@example.org>"
    message["To"] = "some-zope-coders:;"
    message["Date"] = "Date: Mon, 19 May 2003 10:17:36 -0400"
    message["Subject"] = "example"
    message.set_payload("This is just an example\n")

    msgid = delivery.send(fromaddr, toaddrs, message)
    assert ".repoze.sendmail@" in msgid
    assert message["Message-Id"] == msgid


def test_dmd_alternate_transaction_manager():
    mailer = _makeMailerStub()
    delivery = delivery_module.DirectMailDelivery(mailer)
    tm = transaction.TransactionManager()
    delivery.transaction_manager = tm
    fromaddr = "Jim <jim@example.com>"
    toaddrs = ("Guido <guido@example.com>", "Steve <steve@example.com>")
    message = email.message.Message()
    message["From"] = fromaddr
    message["To"] = ",".join(toaddrs)
    message["Date"] = "Date: Mon, 19 May 2003 10:17:36 -0400"
    message["Subject"] = "example"
    message.set_payload("This is just an example\n")

    delivery.send(fromaddr, toaddrs, message)

    transaction.commit()
    assert len(mailer.sent_messages) == 0
    t = tm.get()
    data_manager = t._resources[0]
    assert data_manager.transaction_manager is tm
    t.commit()
    assert len(mailer.sent_messages) == 1
    assert mailer.sent_messages[0][0] == fromaddr
    assert mailer.sent_messages[0][1] == toaddrs
    assert (
        mailer.sent_messages[0][2].get_payload() == "This is just an example\n"
    )

    mailer.sent_messages = []

    delivery.send(fromaddr, toaddrs, message)

    tm.get().abort()
    assert len(mailer.sent_messages) == 0


def _makeMessage():
    message = email.message.Message()
    message["From"] = "Jim <jim@example.org>"
    message["To"] = "some-zope-coders:;"
    message["Date"] = "Date: Mon, 19 May 2003 10:17:36 -0400"
    message["Message-Id"] = "<20030519.1234@example.org>"

    message.set_payload("This is just an example\n")
    return message


def _makeQMD(queuePath="/tmp", **kw):
    return delivery_module.QueuedMailDelivery(queuePath, **kw)


def test_qmd_class_conforms_to_IMailDelivery():
    verify.verifyClass(
        interfaces.IMailDelivery,
        delivery_module.QueuedMailDelivery,
    )


def test_qmd_instance_conforms_to_IMailDelivery():
    verify.verifyObject(interfaces.IMailDelivery, _makeQMD())


def test_qmd_ctor():
    delivery = _makeQMD("/path/to/mailbox")
    assert delivery.queuePath == "/path/to/mailbox"


def test_qmd_ctor_w_tme():
    tm = object()
    delivery = _makeQMD("/path/to/mailbox", transaction_manager=tm)
    assert delivery.queuePath == "/path/to/mailbox"
    assert delivery.transaction_manager is tm


@pytest.fixture
def patched_maildir():
    with mock.patch("repoze.sendmail.delivery.Maildir", MaildirStub):
        yield


def test_qmd_send(patched_maildir):
    delivery = delivery_module.QueuedMailDelivery("/path/to/mailbox")
    fromaddr = "jim@example.com"
    toaddrs = ("guido@example.com", "steve@example.com")
    message = _makeMessage()

    msgid = delivery.send(fromaddr, toaddrs, message)

    assert msgid == "<20030519.1234@example.org>"
    assert MaildirMessageStub.commited_messages == []
    assert MaildirMessageStub.aborted_messages == []

    transaction.commit()

    assert len(MaildirMessageStub.commited_messages) == 1
    assert MaildirMessageStub.aborted_messages == []

    message = MaildirMessageStub.commited_messages[0]

    assert str(message["X-Actually-From"]) == fromaddr
    assert str(message["X-Actually-To"]) == ",".join(toaddrs)

    MaildirMessageStub.commited_messages = []
    message = _makeMessage()

    msgid = delivery.send(fromaddr, toaddrs, message)

    assert "@" in msgid
    assert MaildirMessageStub.commited_messages == []
    assert MaildirMessageStub.aborted_messages == []

    transaction.commit()

    assert len(MaildirMessageStub.commited_messages) == 1
    assert (
        MaildirMessageStub.commited_messages[0].get_payload()
        == "This is just an example\n"
    )
    assert message["Message-Id"] == msgid
    assert message["Message-Id"] == "<20030519.1234@example.org>"
    assert MaildirMessageStub.aborted_messages == []

    MaildirMessageStub.commited_messages = []
    message = _makeMessage()

    msgid = delivery.send(fromaddr, toaddrs, message)

    assert MaildirMessageStub.commited_messages == []
    assert MaildirMessageStub.aborted_messages == []

    transaction.abort()

    assert MaildirMessageStub.commited_messages == []
    assert len(MaildirMessageStub.aborted_messages) == 1


def test_qmd_send_w_non_ASCII_addrs(tmp_path):
    maildir_path = tmp_path / "Maildir"
    qp = queue_module.QueueProcessor(
        _makeMailerStub(),
        maildir_path,
    )
    delivery = _makeQMD(maildir_path)

    non_ascii = b"LaPe\xc3\xb1a".decode("utf-8")
    fromaddr = non_ascii + " <jim@example.com>"
    toaddrs = (non_ascii + " <guido@recip.com>",)
    message = base.MIMEBase("text", "plain")
    message["From"] = fromaddr
    message["To"] = ",".join(toaddrs)

    delivery.send(fromaddr, toaddrs, message)

    assert os.listdir(os.path.join(maildir_path, "tmp"))
    assert not os.listdir(os.path.join(maildir_path, "new"))

    transaction.commit()

    assert not os.listdir(os.path.join(maildir_path, "tmp"))
    assert os.listdir(os.path.join(maildir_path, "new"))

    qp.send_messages()

    assert len(qp.mailer.sent_messages), 1
    queued_fromaddr, queued_toaddrs, queued_message = qp.mailer.sent_messages[
        0
    ]
    assert queued_fromaddr == fromaddr
    assert queued_toaddrs == toaddrs


class MaildirMessageStub:
    message = None
    commited_messages = []  # this list is shared among all instances
    aborted_messages = []  # this one too
    _closed = False

    def __init__(self, message):
        self.message = message

    def commit(self):
        self._commited = True
        self.commited_messages.append(self.message)

    def abort(self):
        self._aborted = True
        self.aborted_messages.append(self.message)


class MaildirStub:
    def __init__(self, path, create=False):
        self.path = path
        self.create = create
        self.msgs = []
        self.files = []

    def __iter__(self):
        return iter(self.files)

    def add(self, message):
        m = MaildirMessageStub(message)
        self.msgs.append(m)
        return m


def _makeMailerStub(*args, **kw):
    implementer(interfaces.IMailer)

    class MailerStub:
        def __init__(self, *args, **kw):
            self.sent_messages = []

        def send(self, fromaddr, toaddrs, message):
            self.sent_messages.append((fromaddr, toaddrs, message))

    return MailerStub(*args, **kw)


class DummyTransaction:
    _resources = ()

    def join(self, resource):
        self._resources += (resource,)
