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
import base64
import quopri
from email import header as email_header
from email import message as email_message
from email.mime import application as email_mime_application
from email.mime import multipart as email_mime_multipart
from email.mime import nonmultipart as email_mime_nonmultipart
from urllib import parse as urllib_parse

from repoze.sendmail import encoding as encoding_module


def test_encode_message_encoding_ascii_headers():
    to = ", ".join(
        [
            "Chris McDonough <chrism@example.com>",
            '"Chris Rossi, M.D." <chrisr@example.com>',
        ]
    )
    message = email_message.Message()
    message["To"] = to
    from_ = "Ross Patterson <rpatterson@example.com>"
    message["From"] = from_
    subject = "I know what you did last PyCon"
    message["Subject"] = subject

    encoded = encoding_module.encode_message(message)

    assert (
        b'To: Chris McDonough <chrism@example.com>, "Chris Rossi,' in encoded
    )
    assert b"From: " + from_.encode("ascii") in encoded
    assert b"Subject: " + subject.encode("ascii") in encoded


def test_encode_message_encoding_latin_1_headers():
    latin_1_encoded = b"LaPe\xf1a"
    latin_1 = latin_1_encoded.decode("iso-8859-1")
    to = ", ".join(
        [
            '"' + latin_1 + ' McDonough, M.D." <chrism@example.com>',
            "Chris Rossi <chrisr@example.com>",
        ]
    )
    message = email_message.Message()
    message["To"] = to
    from_ = latin_1 + " Patterson <rpatterson@example.com>"
    message["From"] = from_
    subject = "I know what you did last " + latin_1
    message["Subject"] = subject

    encoded = encoding_module.encode_message(message)

    assert b"To: =?iso-8859-1?" in encoded
    assert b"From: =?iso-8859-1?" in encoded
    assert b"Subject: =?iso-8859-1?" in encoded
    assert b"<chrism@example.com>" in encoded
    assert b"<chrisr@example.com>" in encoded
    assert b"<rpatterson@example.com>" in encoded


def test_encode_message_encoding_utf_8_headers():
    utf_8_encoded = b"mo \xe2\x82\xac"
    utf_8 = utf_8_encoded.decode("utf-8")
    to = ", ".join(
        [
            '"' + utf_8 + ' McDonough, M.D." <chrism@example.com>',
            "Chris Rossi <chrisr@example.com>",
        ]
    )
    message = email_message.Message()
    message["To"] = to
    from_ = utf_8 + " Patterson <rpatterson@example.com>"
    message["From"] = from_
    subject = "I know what you did last "
    subject_fill = (
        email_header.MAXLINELEN
        - len(b"Subject: " + subject.encode("utf-8") + utf_8_encoded)
        - 18
    )
    subject += "".join("." for idx in range(subject_fill)) + " " + utf_8
    message["Subject"] = subject

    encoded = encoding_module.encode_message(message)
    encoded_subject = "".join(
        email_header.decode_header(line)[0][0].decode("utf-8")
        for line in message["Subject"].split("\n")
    )

    assert b"To: =?utf-8?" in encoded
    assert b"From: =?utf-8?" in encoded
    assert b"Subject: =?utf-8?" in encoded
    assert subject == encoded_subject
    assert b"<chrism@example.com>" in encoded
    assert b"<chrisr@example.com>" in encoded
    assert b"<rpatterson@example.com>" in encoded


def test_encode_message_encoding_ascii_header_parameters():
    message = email_message.Message()
    message["Content-Disposition"] = "attachment; filename=foo.ppt"

    encoded = encoding_module.encode_message(message)

    assert b'Content-Disposition: attachment; filename="foo.ppt"' in encoded


def test_encode_message_encoding_latin_1_header_parameters():
    latin_1_encoded = b"LaPe\xf1a"
    latin_1 = latin_1_encoded.decode("iso-8859-1")
    message = email_message.Message()
    message["Content-Disposition"] = "attachment; filename=" + latin_1 + ".ppt"

    encoded = encoding_module.encode_message(message)

    assert b"Content-Disposition: attachment; filename*=" in encoded
    assert (
        b"iso-8859-1''" + urllib_parse.quote(latin_1_encoded).encode("ascii")
        in encoded
    )


def test_encode_message_encoding_utf_8_header_parameters():
    utf_8_encoded = b"mo \xe2\x82\xac"
    utf_8 = utf_8_encoded.decode("utf-8")
    message = email_message.Message()
    message["Content-Disposition"] = "attachment; filename=" + utf_8 + ".ppt"

    encoded = encoding_module.encode_message(message)

    assert b"Content-Disposition: attachment; filename*=" in encoded
    assert (
        b"utf-8''" + urllib_parse.quote(utf_8_encoded).encode("ascii")
        in encoded
    )


def test_encode_message_encoding_ascii_body():
    body = "I know what you did last PyCon"
    message = email_message.Message()
    message.set_payload(body)

    encoded = encoding_module.encode_message(message)

    assert body.encode("ascii") in encoded


def test_encode_message_encoding_latin_1_body():
    latin_1_encoded = b"LaPe\xf1a"
    latin_1 = latin_1_encoded.decode("iso-8859-1")
    body = "I know what you did last " + latin_1
    message = email_message.Message()
    message.set_payload(body)

    encoded = encoding_module.encode_message(message)

    assert quopri.encodestring(body.encode("iso-8859-1")) in encoded


def test_encode_message_encoding_utf_8_body():
    utf_8_encoded = b"mo \xe2\x82\xac"
    utf_8 = utf_8_encoded.decode("utf-8")
    body = "I know what you did last " + utf_8
    message = email_message.Message()
    message.set_payload(body)

    encoded = encoding_module.encode_message(message)

    assert base64.encodebytes(body.encode("utf-8")) in encoded


def test_encode_message_binary_body():
    body = b"I know what you did last PyCon"
    message = email_mime_multipart.MIMEMultipart()
    message.attach(email_mime_application.MIMEApplication(body))

    encoded = encoding_module.encode_message(message)

    assert base64.encodebytes(body) in encoded


def test_encode_message_encoding_multipart():
    message = email_mime_multipart.MIMEMultipart("alternative")

    utf_8_encoded = b"mo \xe2\x82\xac"
    utf_8 = utf_8_encoded.decode("utf-8")

    plain_string = utf_8
    plain_part = email_mime_nonmultipart.MIMENonMultipart("plain", "plain")
    plain_part.set_payload(plain_string)
    message.attach(plain_part)

    html_string = "<p>" + utf_8 + "</p>"
    html_part = email_mime_nonmultipart.MIMENonMultipart("text", "html")
    html_part.set_payload(html_string)
    message.attach(html_part)

    binary = bytes([x for x in range(256)])
    binary_b64 = base64.encodebytes(binary)
    binary_part = email_mime_application.MIMEApplication(binary)
    message.attach(binary_part)

    encoded = encoding_module.encode_message(message)

    assert base64.encodebytes(plain_string.encode("utf-8")) in encoded
    assert base64.encodebytes(html_string.encode("utf-8")) in encoded
    assert binary_b64 in encoded


def test_encode_message_encoding_multipart_quopri():
    latin_1_encoded = b"LaPe\xf1a"
    latin_1 = latin_1_encoded.decode("latin_1")
    plain_string = "I know what you did last " + latin_1

    message = email_mime_multipart.MIMEMultipart("alternative")

    plain_part = email_mime_nonmultipart.MIMENonMultipart("plain", "plain")
    plain_part.set_payload(plain_string)
    message.attach(plain_part)

    html_string = "<p>" + plain_string + "</p>"
    html_part = email_mime_nonmultipart.MIMENonMultipart("text", "html")
    html_part.set_payload(html_string)
    message.attach(html_part)

    encoded = encoding_module.encode_message(message)

    assert (
        encoded.count(quopri.encodestring(plain_string.encode("latin_1"))) == 2
    )


def test_best_charset_w_ascii():
    value = "foo"
    best, encoded = encoding_module.best_charset(value)
    assert encoded == b"foo"
    assert best == "ascii"


def test_best_charset_w_latin_1():
    latin_1_encoded = b"LaPe\xf1a"
    best, encoded = encoding_module.best_charset(
        latin_1_encoded.decode("iso-8859-1")
    )
    assert best == "iso-8859-1"
    assert encoded == latin_1_encoded


def test_best_charset_w_utf_8():
    utf_8_encoded = b"mo \xe2\x82\xac"
    best, encoded = encoding_module.best_charset(utf_8_encoded.decode("utf-8"))
    assert best == "utf-8"
    assert encoded == utf_8_encoded
