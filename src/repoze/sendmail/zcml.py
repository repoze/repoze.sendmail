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
"""'mail' ZCML Namespaces Schemas

$Id: zcml.py 79091 2007-08-21 18:35:51Z andreasjung $
"""
__docformat__ = 'restructuredtext'

from zope.component import queryUtility
from zope.component import getSiteManager
from zope.configuration.fields import Path
from zope.configuration.exceptions import ConfigurationError
from zope.interface import Interface
from zope.schema import TextLine
from zope.schema import BytesLine
from zope.schema import Int
from zope.schema import Bool

from repoze.sendmail.delivery import QueuedMailDelivery
from repoze.sendmail.delivery import DirectMailDelivery
from repoze.sendmail.queue import QueueProcessor
from repoze.sendmail.interfaces import IMailer
from repoze.sendmail.interfaces import IMailDelivery
from repoze.sendmail.mailer import SMTPMailer

def handler(methodName, *args, **kwargs):
    method = getattr(getSiteManager(), methodName)
    method(*args, **kwargs)

class IDeliveryDirective(Interface):
    """This abstract directive describes a generic mail delivery utility
    registration."""

    name = TextLine(
        title=u"Name",
        description=u'Specifies the Delivery name of the mail utility. '\
                    u'The default is "Mail".',
        default=u"Mail",
        required=False)

    mailer = TextLine(
        title=u"Mailer",
        description=u"Defines the mailer to be used for sending mail.",
        required=True)


class IQueuedDeliveryDirective(IDeliveryDirective):
    """This directive creates and registers a global queued mail utility. It
    should be only called once during startup."""

    queuePath = Path(
        title=u"Queue Path",
        description=u"Defines the path for the queue directory.",
        required=True)

    processorThread = Bool(
        title=u"Run Queue Processor Thread",
        description=u"""Indicates whether to run queue processor in a thread
                     in this process.
                     """,
        required=False,
        default=False)
    
def queuedDelivery(_context, queuePath, mailer, 
                   processorThread=False, name="Mail"):

    def createQueuedDelivery():
        delivery = QueuedMailDelivery(queuePath)

        handler('registerUtility', delivery, IMailDelivery, name)

        mailerObject = queryUtility(IMailer, mailer)
        if mailerObject is None:
            raise ConfigurationError("Mailer %r is not defined" %mailer)

        if processorThread:
            qp = QueueProcessor()
            qp.mailer = mailerObject
            qp.queue_path = queuePath
            delivery.processor_thread = qp.send_messages_thread()
            
    _context.action(
            discriminator = ('delivery', name),
            callable = createQueuedDelivery,
            args = () )

class IDirectDeliveryDirective(IDeliveryDirective):
    """This directive creates and registers a global direct mail utility. It
    should be only called once during startup."""

def directDelivery(_context, mailer, name="Mail"):

    def createDirectDelivery():
        mailerObject = queryUtility(IMailer, mailer)
        if mailerObject is None:
            raise ConfigurationError("Mailer %r is not defined" %mailer)

        delivery = DirectMailDelivery(mailerObject)

        handler('registerUtility', delivery, IMailDelivery, name)

    _context.action(
            discriminator = ('utility', IMailDelivery, name),
            callable = createDirectDelivery,
            args = () )

class IMailerDirective(Interface):
    """A generic directive registering a mailer for the mail utility."""

    name = TextLine(
        title=u"Name",
        description=u"Name of the Mailer.",
        required=True)


class ISMTPMailerDirective(IMailerDirective):
    """Registers a new SMTP mailer."""

    hostname = BytesLine(
        title=u"Hostname",
        description=u"Hostname of the SMTP host.",
        default="localhost",
        required=False)

    port = Int(
        title=u"Port",
        description=u"Port of the SMTP server.",
        default=25,
        required=False)

    username = TextLine(
        title=u"Username",
        description=u"A username for SMTP AUTH.",
        required=False)

    password = TextLine(
        title=u"Password",
        description=u"A password for SMTP AUTH.",
        required=False)

def smtpMailer(_context, name, hostname="localhost", port="25",
               username=None, password=None):
    _context.action(
        discriminator = ('utility', IMailer, name),
        callable = handler,
        args = ('registerUtility',
                SMTPMailer(hostname, port, username, password), IMailer, name)
        )
