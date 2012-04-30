# Python 2/3 straddling.
import base64
import codecs

try:
    text_type = unicode
except NameError: #pragma NO COVER
    PY_2 = False
    text_type = str
    def b(x):
        return codecs.latin_1_encode(x)[0]
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
