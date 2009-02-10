##############################################################################
#
# Copyright (c) 2006 Zope Corporation and Contributors.
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
"""Mail vocabularies

$Id: vocabulary.py 92953 2008-11-15 00:23:04Z hannosch $
"""
__docformat__ = 'restructuredtext'

import zope.component
from zope.interface import classProvides
from zope.interface import implements
from zope.interface import Interface
from zope.schema.interfaces import ITokenizedTerm
from zope.schema.interfaces import IVocabularyFactory
from zope.schema.interfaces import IVocabularyTokenized
from repoze.sendmail.interfaces import IMailDelivery


class UtilityTerm(object):
    """A term representing a utility.

    The token of the term is the name of the utility. Here is a brief example
    on how the IVocabulary interface is handled in this term as a
    utility:
    
    >>> from zope.interface.verify import verifyObject
    >>> from zope.schema.interfaces import IVocabulary
    >>> term = UtilityTerm(IVocabulary, 'zope.schema.interfaces.IVocabulary')
    >>> verifyObject(ITokenizedTerm, term)
    True

    >>> term.value
    <InterfaceClass zope.schema.interfaces.IVocabulary>
    >>> term.token
    'zope.schema.interfaces.IVocabulary'

    >>> term
    <UtilityTerm zope.schema.interfaces.IVocabulary, instance of InterfaceClass>
    """
    implements(ITokenizedTerm)

    def __init__(self, value, token):
        """Create a term for value and token."""
        self.value = value
        self.token = token

    def __repr__(self):
        return '<UtilityTerm %s, instance of %s>' %(
            self.token, self.value.__class__.__name__)


class UtilityVocabulary(object):
    """Vocabulary that provides utilities of a specified interface.

    Here is a short example of how the vocabulary should work.

    First we need to create a utility interface and some utilities:

    >>> class IObject(Interface):
    ...     'Simple interface to mark object utilities.'

    >>> class Object(object):
    ...     implements(IObject)
    ...     def __init__(self, name):
    ...         self.name = name
    ...     def __repr__(self):
    ...         return '<Object %s>' %self.name

    Now we register some utilities for IObject

    >>> from zope.component import provideUtility
    >>> object1 = Object('object1')
    >>> provideUtility(object1, name='object1')
    >>> object2 = Object('object2')
    >>> provideUtility(object2, name='object2')
    >>> object3 = Object('object3')
    >>> provideUtility(object3, name='object3')
    >>> object4 = Object('object4')

    We are now ready to create a vocabulary that we can use; in our case
    everything is global, so the context is None.

    >>> vocab = UtilityVocabulary(None, interface=IObject)
    >>> import pprint
    >>> pprint.pprint(vocab._terms.items())
    [(u'object1', <UtilityTerm object1, instance of Object>),
     (u'object2', <UtilityTerm object2, instance of Object>),
     (u'object3', <UtilityTerm object3, instance of Object>)]

    Now let's see how the other methods behave in this context. First we can
    just use the 'in' opreator to test whether a value is available.

    >>> object1 in vocab
    True
    >>> object4 in vocab
    False

    We can also create a lazy iterator. Note that the utility terms might
    appear in a different order than the utilities were registered.

    >>> iterator = iter(vocab)
    >>> terms = list(iterator)
    >>> names = [term.token for term in terms]
    >>> names.sort()
    >>> names
    [u'object1', u'object2', u'object3']

    Determining the amount of utilities available via the vocabulary is also
    possible.

    >>> len(vocab)
    3
    """
    implements(IVocabularyTokenized)
    classProvides(IVocabularyFactory)

    # override these in subclasses
    interface = Interface
    nameOnly = False

    def __init__(self, context, **kw):
        utils = zope.component.getUtilitiesFor(self.interface, context)
        self._terms = dict(
            (name, UtilityTerm(self.nameOnly and name or util, name))
            for name, util in utils)

    def __contains__(self, value):
        """See zope.schema.interfaces.IBaseVocabulary"""
        return value in (term.value for term in self._terms.values())

    def getTerm(self, value):
        """See zope.schema.interfaces.IBaseVocabulary"""
        try:
            return [term for name, term in self._terms.items()
                    if term.value == value][0]
        except IndexError:
            raise LookupError(value)

    def getTermByToken(self, token):
        """See zope.schema.interfaces.IVocabularyTokenized"""
        try:
            return self._terms[token]
        except KeyError:
            raise LookupError(token)

    def __iter__(self):
        """See zope.schema.interfaces.IIterableVocabulary"""
        # Sort the terms by the token (utility name)
        values = self._terms.values()
        values.sort(lambda x, y: cmp(x.token, y.token))
        return iter(values)

    def __len__(self):
        """See zope.schema.interfaces.IIterableVocabulary"""
        return len(self._terms)


class MailDeliveryNames(UtilityVocabulary):
    """Vocabulary with names of mail delivery utilities

    Let's provide a few stub utilities:

      >>> from zope.interface import implements
      >>> class StubMailDelivery(object):
      ...     implements(IMailDelivery)

      >>> from zope.component import provideUtility
      >>> for name in 'and now for something completely different'.split():
      ...     provideUtility(StubMailDelivery(), name=name)

    Let's also provide another utility to verify that we only see mail
    delivery utilities:

      >>> provideUtility(MailDeliveryNames, name='Mail Delivery Names')

    Let's see what's in the vocabulary:

      >>> vocabulary = MailDeliveryNames(None)
      >>> names = [term.value for term in vocabulary]
      >>> names.sort()
      >>> print ' '.join(names)
      and completely different for now something
    """
    classProvides(IVocabularyFactory)
    interface = IMailDelivery
    nameOnly = True
