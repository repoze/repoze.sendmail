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

import os
import shutil
import unittest
import tempfile
import time

import zope.component
from zope.component.testing import PlacelessSetup
from zope.configuration import xmlconfig
from zope.interface import implements

from repoze.sendmail.interfaces import IMailDelivery, IMailer
from repoze.sendmail.queue import QueueProcessor
from repoze.sendmail import delivery
import repoze.sendmail.tests


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

    def tearDown(self):
        delivery.Maildir = self.orig_maildir

        shutil.rmtree(self.mailbox, True)
        super(DirectivesTest, self).tearDown()

    def testQueuedDelivery(self):
        delivery = zope.component.getUtility(IMailDelivery, "Mail")
        self.assertEqual('QueuedMailDelivery', delivery.__class__.__name__)
        self.assertEqual(self.mailbox, delivery.queuePath)

    def testDirectDelivery(self):
        delivery = zope.component.getUtility(IMailDelivery, "Mail2")
        self.assertEqual('DirectMailDelivery', delivery.__class__.__name__)
        self.assert_(self.testMailer is delivery.mailer)
