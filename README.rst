`repoze.sendmail` README
========================

.. image:: https://travis-ci.org/repoze/repoze.sendmail.png?branch=master
        :target: https://travis-ci.org/repoze/repoze.sendmail

.. image:: https://img.shields.io/pypi/v/repoze.sendmail.svg
        :target: https://pypi.python.org/pypi/repoze.sendmail

.. image:: https://img.shields.io/pypi/pyversions/repoze.sendmail.svg
        :target: https://pypi.python.org/pypi/repoze.sendmail

`repoze.sendmail` allows coupling the sending of email messages with a
transaction, using the Zope transaction manager.  This allows messages to
only be sent out when and if a transaction is committed, preventing users
from receiving notifications about events which may not have completed
successfully.

Please see `docs/index.rst` for complete documentation, or read the
docs online at http://docs.repoze.org/sendmail
