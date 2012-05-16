# Python 2/3 straddling.
import base64
import codecs

try:
    text_type = unicode
    def from_octets(seq_of_ints):
        return ''.join([chr(x) for x in seq_of_ints])
except NameError: #pragma NO COVER
    PY_2 = False
    text_type = str
    def b(x):
        return codecs.latin_1_encode(x)[0]
    def from_octets(seq_of_ints):
        return bytes(seq_of_ints)
else:
    PY_2 = True
    b = str

try:
    from ssl import SSLError
except ImportError: #pragma NO COVER  Python 2.5
    from socket import sslerror as SSLError

try:
    from configparser import ConfigParser
except ImportError: #pragma NO COVER Python 2
    from ConfigParser import ConfigParser

try:
    from urllib.parse import quote
except ImportError: #pragma NO COVER Python 2
    from urllib import quote

if PY_2: # pragma: no cover
    encodestring = base64.encodestring
else: # pragma: no cover
    encodestring = base64.encodebytes
