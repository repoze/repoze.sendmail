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
"""Collection of possible Mail Events.

$Id: event.py 66922 2006-04-12 23:28:07Z jinty $
"""
__docformat__ = 'restructuredtext'

from zope.interface import implements

from repoze.sendmail.interfaces import IMailSentEvent, IMailErrorEvent


class MailSentEvent(object):
    __doc__ = IMailSentEvent.__doc__

    implements(IMailSentEvent)

    def __init__(self, messageId):
        self.messageId = messageId


class MailErrorEvent(object):
    __doc__ = IMailErrorEvent.__doc__

    implements(IMailErrorEvent)

    def __init__(self, messageId, errorMessage):
        self.messageId = messageId
        self.errorMessage = errorMessage
