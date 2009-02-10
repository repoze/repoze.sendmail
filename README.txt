=============
repoze.sendmail
=============

repoze.sendmail is a fork of zope.sendmail with dependency on zope security
framework removed.  The idea being that in this case authorization should be
handled by caller, not by this library, which simply provides a means to send
email.  This fork is meant to be usable with repoze.bfg and other non-Zope3
frameworks.

For usage and other documentation, see documentation for zope.sendmail:

http://pypi.python.org/pypi/zope.sendmail

See also src/repoze/sendmail/README.txt

