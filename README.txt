===============
repoze.sendmail
===============

repoze.sendmail is a fork of zope.sendmail with dependency on zope security
framework removed.  The idea being that in this case authorization should be
handled by caller, not by this library, which simply provides a means to send
email.  This fork is meant to be usable with repoze.bfg and other non-Zope3
frameworks.

We have also made optional, for queued delivery, the running of the queue 
processor thread.  We have added a console script, qp, which can process queued
mail and either exit after one pass or continue to run daemonically, checking
the queue periodically.  

You probably want to take a look at the documentation for zope.sendmail:

http://pypi.python.org/pypi/zope.sendmail

See also src/repoze/sendmail/README.txt

==============
Basic Tutorial
==============

To use repoze.sendmail using the component architecture, you'll need to add
something like this to your project's zcml:

.. code-block: xml
   :linenos:

  <configure xmlns="..."
             xmlns:mail="http://namespaces.repoze.org/mail"
  >
  ...
  
  <include package="repoze.sendmail" file="meta.zcml"/>
  
  <mail:smtpMailer
    name="smtp"
    hostname="localhost"
    port="25"
    />
    
  <mail:queuedDelivery
    name="myapp.mailer"
    mailer="smtp"
    queuePath="/my/var/mailqueue"
    processorThread="False"
    />

  </configure>

Note that the queuePath in the queuedDelivery must exist on the filesystem.  
This creates two utilities, a mailer, named smtp, and a delivery, named 
myapp.mailer.  The mailer is used by the delivery mechanism, so generally in 
your code you need only look up the delivery utility::

  def send_email(msg):
      mailer = getUtility(IMailDelivery, 'bfgtest.mailer')
      mailer.send(sender, [recipient], msg.as_string())

The message is an instance of email.MIMEText.MIMEText::

  import email.MIMEText
  def create_message(sender, recipient, subject, body):
      msg = email.MIMEText.MIMEText(body.encode('UTF-8'), 'plain', 'UTF-8')
      msg["From"] = sender
      msg["To"] = recipient
      msg["Subject"] = email.Header.Header(subject, 'UTF-8')
      return msg
    
repoze.sendmail hooks into the transaction system and only sends queued 
messages on transaction commit.  If you are using a framework which, like 
repoze.bfg, does not use transactions by default, you will need to begin and
commit a transaction of your own in order for mail to be sent::

  import transaction
  transaction.manager.begin()
  try:
      my_code_here()
      transaction.manager.commit()
  except e:
      transaction.manager.abort()
      raise e
