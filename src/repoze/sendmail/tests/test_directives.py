##############################################################################
#
# Copyright (c) 2001, 2002 Zope Corporation and Contributors.
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
"""Test the gts ZCML namespace directives.

$Id: test_directives.py 80961 2007-10-23 14:54:54Z fdrake $
"""
import os
import shutil
import unittest
import threading
import tempfile
import time

import zope.component
from zope.component.testing import PlacelessSetup
from zope.configuration import xmlconfig
from zope.interface import implements

from repoze.sendmail.interfaces import \
     IMailDelivery, IMailer, ISMTPMailer
from repoze.sendmail.queue import QueueProcessor
from repoze.sendmail import delivery
import repoze.sendmail.tests


class MaildirStub(object):

    def __init__(self, path, create=False):
        self.path = path
        self.create = create

    def __iter__(self):
        return iter(())

    def newMessage(self):
        return None

class Mailer(object):
    implements(IMailer)


class DirectivesTest(PlacelessSetup, unittest.TestCase):

    def setUp(self):
        self.mailbox = os.path.join(tempfile.mkdtemp(), "mailbox")

        super(DirectivesTest, self).setUp()
        self.testMailer = Mailer()

        gsm = zope.component.getGlobalSiteManager()
        gsm.registerUtility(Mailer(), IMailer, "test.smtp")
        gsm.registerUtility(self.testMailer, IMailer, "test.mailer")

        here = os.path.dirname(__file__)
        zcmlfile = open(os.path.join(here, "mail.zcml"), 'r')
        zcml = zcmlfile.read()
        zcmlfile.close()

        self.context = xmlconfig.string(
            zcml.replace('path/to/tmp/mailbox', self.mailbox))
        self.orig_maildir = delivery.Maildir
        delivery.Maildir = MaildirStub

    def tearDown(self):
        delivery.Maildir = self.orig_maildir

        # Tear down the mail queue processor thread.
        # Give the other thread a chance to start:
        time.sleep(0.001)
        threads = list(threading.enumerate())
        for thread in threads:
            name = getattr(thread, "name", None)
            if name == "repoze.sendmail.QueueProcessorThread":
                thread.queue_processor.stop()
                thread.join()

        shutil.rmtree(self.mailbox, True)
        super(DirectivesTest, self).tearDown()

    def testQueuedDelivery(self):
        delivery = zope.component.getUtility(IMailDelivery, "Mail")
        self.assertEqual('QueuedMailDelivery', delivery.__class__.__name__)
        self.assertEqual(self.mailbox, delivery.queuePath)
        self.assertEquals(None, delivery.processor_thread)
        
    def testQueuedDeliveryWithProcessorThread(self):
        delivery = zope.component.getUtility(IMailDelivery, 
                                              "MailWithProcessorThread")
        self.assertEqual("QueuedMailDelivery", delivery.__class__.__name__)
        self.assertEqual(self.mailbox, delivery.queuePath)
        self.assertNotEqual(None, delivery.processor_thread)
        
    def testDirectDelivery(self):
        delivery = zope.component.getUtility(IMailDelivery, "Mail2")
        self.assertEqual('DirectMailDelivery', delivery.__class__.__name__)
        self.assert_(self.testMailer is delivery.mailer)

    def testSMTPMailer(self):
        mailer = zope.component.getUtility(IMailer, "smtp")
        self.assert_(ISMTPMailer.providedBy(mailer))


def test_suite():
    return unittest.TestSuite((
        unittest.makeSuite(DirectivesTest),
        ))

if __name__ == '__main__':
    unittest.main()
