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
import base64
import quopri
import sys

from email import message
from email.mime import multipart
from email.mime import application

# BBB Python 2.5 & 3 compat
b = str
try:
    unicode
except NameError: # pragma: no cover
    import codecs
    def b(x): return codecs.latin_1_encode(x)[0]

try:
    from urllib.parse import quote
except ImportError:
    # BBB Python 2 and 3 compat
    from urllib import quote

if sys.version_info[0] == 3: # pragma: no cover
    encodestring = base64.encodebytes
else:
    encodestring = base64.encodestring


class TestEncoding(unittest.TestCase):

    def setUp(self):
        self.message = message.Message()
        self.latin_1_encoded = b('LaPe\xf1a')
        self.latin_1 = self.latin_1_encoded.decode('latin_1')
        self.utf_8_encoded = b('mo \xe2\x82\xac')
        self.utf_8 = self.utf_8_encoded.decode('utf_8')

    def encode(self, message=None):
        if message is None:
            message = self.message
        from repoze.sendmail import encoding
        return encoding.encode_message(message)

    def test_best_charset_ascii(self):
        from repoze.sendmail import encoding
        value = 'foo'
        best, encoded = encoding.best_charset(value)
        self.assertEqual(encoded, b('foo'))
        self.assertEqual(best, 'ascii')

    def test_best_charset_latin_1(self):
        from repoze.sendmail import encoding
        value = self.latin_1
        best, encoded = encoding.best_charset(value)
        self.assertEqual(encoded, self.latin_1_encoded)
        self.assertEqual(best, 'latin_1')

    def test_best_charset_utf_8(self):
        from repoze.sendmail import encoding
        value = self.utf_8
        best, encoded = encoding.best_charset(value)
        self.assertEqual(encoded, self.utf_8_encoded)
        self.assertEqual(best, 'utf_8')
    
    def test_encoding_ascii_headers(self):
        to = ', '.join(['Chris McDonough <chrism@example.com>',
                        '"Chris Rossi, M.D." <chrisr@example.com>'])
        self.message['To'] = to
        from_ = 'Ross Patterson <rpatterson@example.com>'
        self.message['From'] = from_
        subject = 'I know what you did last PyCon'
        self.message['Subject'] = subject

        encoded = self.encode()

        self.assertTrue(
            b('To: Chris McDonough <chrism@example.com>, "Chris Rossi,')
            in encoded)
        self.assertTrue(b('From: ')+from_.encode('ascii') in encoded)
        self.assertTrue(b('Subject: ')+subject.encode('ascii') in encoded)

    def test_encoding_latin_1_headers(self):
        to = ', '.join([
            '"'+self.latin_1+' McDonough, M.D." <chrism@example.com>',
            'Chris Rossi <chrisr@example.com>'])
        self.message['To'] = to
        from_ = self.latin_1+' Patterson <rpatterson@example.com>'
        self.message['From'] = from_
        subject = 'I know what you did last '+self.latin_1
        self.message['Subject'] = subject

        encoded = self.encode()

        self.assertTrue(b('To: =?iso-8859-1?') in encoded)
        self.assertTrue(b('From: =?iso-8859-1?') in encoded)
        self.assertTrue(b('Subject: =?iso-8859-1?') in encoded)
        self.assertTrue(b('<chrism@example.com>') in encoded)
        self.assertTrue(b('<chrisr@example.com>') in encoded)
        self.assertTrue(b('<rpatterson@example.com>') in encoded)

    def test_encoding_utf_8_headers(self):
        to = ', '.join([
            '"'+self.utf_8+' McDonough, M.D." <chrism@example.com>',
            'Chris Rossi <chrisr@example.com>'])
        self.message['To'] = to
        from_ = self.utf_8+' Patterson <rpatterson@example.com>'
        self.message['From'] = from_
        subject = 'I know what you did last '+self.utf_8
        self.message['Subject'] = subject

        encoded = self.encode()

        self.assertTrue(b('To: =?utf') in encoded)
        self.assertTrue(b('From: =?utf') in encoded)
        self.assertTrue(b('Subject: =?utf') in encoded)
        self.assertTrue(b('<chrism@example.com>') in encoded)
        self.assertTrue(b('<chrisr@example.com>') in encoded)
        self.assertTrue(b('<rpatterson@example.com>') in encoded)
    
    def test_encoding_ascii_header_parameters(self):
        self.message['Content-Disposition'] = (
            'attachment; filename=foo.ppt')

        encoded = self.encode()
        
        self.assertTrue(
            b('Content-Disposition: attachment; filename="foo.ppt"')
            in encoded)
    
    def test_encoding_latin_1_header_parameters(self):
        self.message['Content-Disposition'] = (
            'attachment; filename='+self.latin_1+'.ppt')

        encoded = self.encode()
        
        self.assertTrue(
            b("Content-Disposition: attachment; filename*=") in encoded)
        self.assertTrue(b("latin_1''")+quote(
            self.latin_1_encoded).encode('ascii') in encoded)
    
    def test_encoding_utf_8_header_parameters(self):
        self.message['Content-Disposition'] = (
            'attachment; filename='+self.utf_8+'.ppt')

        encoded = self.encode()
        
        self.assertTrue(
            b("Content-Disposition: attachment; filename*=") in encoded)
        self.assertTrue(b("utf_8''")+quote(self.utf_8_encoded).encode('ascii')
                        in encoded)

    def test_encoding_ascii_body(self):
        body = 'I know what you did last PyCon'
        self.message.set_payload(body)

        encoded = self.encode()

        self.assertTrue(body.encode('ascii') in encoded)

    def test_encoding_latin_1_body(self):
        body = 'I know what you did last '+self.latin_1
        self.message.set_payload(body)

        encoded = self.encode()

        self.assertTrue(quopri.encodestring(body.encode('latin_1')) in encoded)

    def test_encoding_utf_8_body(self):
        body = 'I know what you did last '+self.utf_8
        self.message.set_payload(body)

        encoded = self.encode()

        self.assertTrue(encodestring(body.encode('utf_8')) in encoded)

    def test_binary_body(self):
        body = b('I know what you did last PyCon')
        self.message = multipart.MIMEMultipart()
        self.message.attach(application.MIMEApplication(body))

        encoded = self.encode()

        self.assertTrue(encodestring(body) in encoded)
