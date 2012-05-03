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


class Test_best_charset(unittest.TestCase):

    def _callFUT(self, *args, **kw):
        from repoze.sendmail.encoding import best_charset
        return best_charset(*args, **kw)

    def test_w_ascii(self):
        from repoze.sendmail._compat import b
        value = 'foo'
        best, encoded = self._callFUT(value)
        self.assertEqual(encoded, b('foo'))
        self.assertEqual(best, 'ascii')

    def test_w_latin_1(self):
        from repoze.sendmail._compat import b
        latin_1_encoded = b('LaPe\xf1a')
        best, encoded = self._callFUT(latin_1_encoded.decode('latin_1'))
        self.assertEqual(best, 'latin_1')
        self.assertEqual(encoded, latin_1_encoded)

    def test_w_utf_8(self):
        from repoze.sendmail._compat import b
        utf_8_encoded = b('mo \xe2\x82\xac')
        best, encoded = self._callFUT(utf_8_encoded.decode('utf_8'))
        self.assertEqual(best, 'utf_8')
        self.assertEqual(encoded, utf_8_encoded)


class TestEncoding(unittest.TestCase):

    def _callFUT(self, message):
        from repoze.sendmail.encoding import encode_message
        return encode_message(message)

    def _makeMessage(self):
        from email.message import Message
        return Message()
    
    def test_encoding_ascii_headers(self):
        from repoze.sendmail._compat import b
        to = ', '.join(['Chris McDonough <chrism@example.com>',
                        '"Chris Rossi, M.D." <chrisr@example.com>'])
        message = self._makeMessage()
        message['To'] = to
        from_ = 'Ross Patterson <rpatterson@example.com>'
        message['From'] = from_
        subject = 'I know what you did last PyCon'
        message['Subject'] = subject

        encoded = self._callFUT(message)

        self.assertTrue(
            b('To: Chris McDonough <chrism@example.com>, "Chris Rossi,')
            in encoded)
        self.assertTrue(b('From: ')+from_.encode('ascii') in encoded)
        self.assertTrue(b('Subject: ')+subject.encode('ascii') in encoded)

    def test_encoding_latin_1_headers(self):
        from repoze.sendmail._compat import b
        latin_1_encoded = b('LaPe\xf1a')
        latin_1 = latin_1_encoded.decode('latin_1')
        to = ', '.join([
            '"' + latin_1 + ' McDonough, M.D." <chrism@example.com>',
            'Chris Rossi <chrisr@example.com>'])
        message = self._makeMessage()
        message['To'] = to
        from_ = latin_1 + ' Patterson <rpatterson@example.com>'
        message['From'] = from_
        subject = 'I know what you did last ' + latin_1
        message['Subject'] = subject

        encoded = self._callFUT(message)

        self.assertTrue(b('To: =?iso-8859-1?') in encoded)
        self.assertTrue(b('From: =?iso-8859-1?') in encoded)
        self.assertTrue(b('Subject: =?iso-8859-1?') in encoded)
        self.assertTrue(b('<chrism@example.com>') in encoded)
        self.assertTrue(b('<chrisr@example.com>') in encoded)
        self.assertTrue(b('<rpatterson@example.com>') in encoded)

    def test_encoding_utf_8_headers(self):
        from repoze.sendmail._compat import b
        utf_8_encoded = b('mo \xe2\x82\xac')
        utf_8 = utf_8_encoded.decode('utf_8')
        to = ', '.join([
            '"' + utf_8 + ' McDonough, M.D." <chrism@example.com>',
            'Chris Rossi <chrisr@example.com>'])
        message = self._makeMessage()
        message['To'] = to
        from_ = utf_8 + ' Patterson <rpatterson@example.com>'
        message['From'] = from_
        subject = 'I know what you did last ' + utf_8
        message['Subject'] = subject

        encoded = self._callFUT(message)

        self.assertTrue(b('To: =?utf') in encoded)
        self.assertTrue(b('From: =?utf') in encoded)
        self.assertTrue(b('Subject: =?utf') in encoded)
        self.assertTrue(b('<chrism@example.com>') in encoded)
        self.assertTrue(b('<chrisr@example.com>') in encoded)
        self.assertTrue(b('<rpatterson@example.com>') in encoded)
    
    def test_encoding_ascii_header_parameters(self):
        from repoze.sendmail._compat import b
        message = self._makeMessage()
        message['Content-Disposition'] = 'attachment; filename=foo.ppt'

        encoded = self._callFUT(message)
        
        self.assertTrue(
            b('Content-Disposition: attachment; filename="foo.ppt"')
            in encoded)
    
    def test_encoding_latin_1_header_parameters(self):
        from repoze.sendmail._compat import b
        from repoze.sendmail._compat import quote
        latin_1_encoded = b('LaPe\xf1a')
        latin_1 = latin_1_encoded.decode('latin_1')
        message = self._makeMessage()
        message['Content-Disposition'] = (
            'attachment; filename=' + latin_1 + '.ppt')

        encoded = self._callFUT(message)
        
        self.assertTrue(
            b("Content-Disposition: attachment; filename*=") in encoded)
        self.assertTrue(b("latin_1''") + quote(latin_1_encoded).encode('ascii')
                        in encoded)
    
    def test_encoding_utf_8_header_parameters(self):
        from repoze.sendmail._compat import b
        from repoze.sendmail._compat import quote
        utf_8_encoded = b('mo \xe2\x82\xac')
        utf_8 = utf_8_encoded.decode('utf_8')
        message = self._makeMessage()
        message['Content-Disposition'] = (
            'attachment; filename=' + utf_8 +'.ppt')

        encoded = self._callFUT(message)
        
        self.assertTrue(
            b("Content-Disposition: attachment; filename*=") in encoded)
        self.assertTrue(b("utf_8''") + quote(utf_8_encoded).encode('ascii')
                        in encoded)

    def test_encoding_ascii_body(self):
        body = 'I know what you did last PyCon'
        message = self._makeMessage()
        message.set_payload(body)

        encoded = self._callFUT(message)

        self.assertTrue(body.encode('ascii') in encoded)

    def test_encoding_latin_1_body(self):
        import quopri
        from repoze.sendmail._compat import b
        latin_1_encoded = b('LaPe\xf1a')
        latin_1 = latin_1_encoded.decode('latin_1')
        body = 'I know what you did last ' + latin_1
        message = self._makeMessage()
        message.set_payload(body)

        encoded = self._callFUT(message)

        self.assertTrue(quopri.encodestring(body.encode('latin_1')) in encoded)

    def test_encoding_utf_8_body(self):
        from repoze.sendmail._compat import b
        from repoze.sendmail._compat import encodestring
        utf_8_encoded = b('mo \xe2\x82\xac')
        utf_8 = utf_8_encoded.decode('utf_8')
        body = 'I know what you did last '+ utf_8
        message = self._makeMessage()
        message.set_payload(body)

        encoded = self._callFUT(message)

        self.assertTrue(encodestring(body.encode('utf_8')) in encoded)

    def test_binary_body(self):
        from email.mime import application
        from email.mime import multipart
        from repoze.sendmail._compat import encodestring
        from repoze.sendmail._compat import b
        body = b('I know what you did last PyCon')
        message = multipart.MIMEMultipart()
        message.attach(application.MIMEApplication(body))

        encoded = self._callFUT(message)

        self.assertTrue(encodestring(body) in encoded)

    def test_encoding_multipart(self):
        from email.mime import multipart
        from email.mime import nonmultipart
        from repoze.sendmail._compat import encodestring
        from repoze.sendmail._compat import b

        message = multipart.MIMEMultipart('alternative')

        utf_8_encoded = b('mo \xe2\x82\xac')
        utf_8 = utf_8_encoded.decode('utf_8')

        plain_string = utf_8
        plain_part = nonmultipart.MIMENonMultipart('plain', 'plain')
        plain_part.set_payload(plain_string)
        message.attach(plain_part)

        html_string = '<p>'+utf_8+'</p>'
        html_part = nonmultipart.MIMENonMultipart('text', 'html')
        html_part.set_payload(html_string)
        message.attach(html_part)

        encoded = self._callFUT(message)

        self.assertTrue(encodestring(plain_string.encode('utf_8')) in encoded)
        self.assertTrue(encodestring(html_string.encode('utf_8')) in encoded)
