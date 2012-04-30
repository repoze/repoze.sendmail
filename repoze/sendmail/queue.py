import errno
import logging
import os
import smtplib
import stat
import sys
import time

from email.parser import Parser
from email import header

from repoze.sendmail.maildir import Maildir
from repoze.sendmail.mailer import SMTPMailer
from repoze.sendmail._compat import ConfigParser

if sys.platform == 'win32': #pragma NO COVERAGE
    import win32file
    _os_link = lambda src, dst: win32file.CreateHardLink(dst, src, None)
else:
    _os_link = os.link

def _log_error(msg): #pragma NO COVER
    sys.stderr.write(msg)

# The below diagram depicts the operations performed while sending a message.
# This sequence of operations will be performed for each file in the maildir
# on which ``send_message`` is called.
#
# Any error conditions not depected on the diagram will provoke the catch-all
# exception logging of the ``send_message`` method.
#
# In the diagram the "message file" is the file in the maildir's "cur" directory
# that contains the message and "tmp file" is a hard link to the message file
# created in the maildir's "tmp" directory.
#
#           ( start trying to deliver a message )
#                            |
#                            |
#                            V
#            +-----( get tmp file mtime )
#            |               |
#            |               | file exists
#            |               V
#            |         ( check age )-----------------------------+
#   tmp file |               |                       file is new |
#   does not |               | file is old                       |
#   exist    |               |                                   |
#            |      ( unlink tmp file )-----------------------+  |
#            |               |                      file does |  |
#            |               | file unlinked        not exist |  |
#            |               V                                |  |
#            +---->( touch message file )------------------+  |  |
#                            |                   file does |  |  |
#                            |                   not exist |  |  |
#                            V                             |  |  |
#            ( link message file to tmp file )----------+  |  |  |
#                            |                 tmp file |  |  |  |
#                            |           already exists |  |  |  |
#                            |                          |  |  |  |
#                            V                          V  V  V  V
#                     ( send message )             ( skip this message )
#                            |
#                            V
#                 ( unlink message file )---------+
#                            |                    |
#                            | file unlinked      | file no longer exists
#                            |                    |
#                            |  +-----------------+
#                            |  |
#                            |  V
#                  ( unlink tmp file )------------+
#                            |                    |
#                            | file unlinked      | file no longer exists
#                            V                    |
#                  ( message delivered )<---------+


# The longest time sending a file is expected to take.  Longer than this and
# the send attempt will be assumed to have failed.  This means that sending
# very large files or using very slow mail servers could result in duplicate
# messages sent.
MAX_SEND_TIME = 60*60*3

def boolean(s):
    s = str(s).lower()
    return s.startswith("t") or s.startswith("y") or s.startswith("1")

def string_or_none(s):
    if s == 'None':
        return None
    return s

class QueueProcessor(object):
    log = logging.getLogger("QueueProcessor")

    def __init__(self, mailer, queue_path, Maildir=Maildir):
        self.mailer = mailer
        self.maildir = Maildir(queue_path, create=True)

    def send_messages(self):
        for filename in self.maildir:
            self._send_message(filename)

    def _parseMessage(self, fp):
        """
        Extract fromaddr and toaddrs from the X-Actually-{To,From} headers.
        Returns message string which has those headers stripped.
        """
        parser = Parser()
        message = parser.parse(fp)

        fromaddr = message['X-Actually-From']
        if fromaddr is not None:
            decoded_fromaddr = header.decode_header(fromaddr)
            assert len(decoded_fromaddr) == 1, 'From header has multiple parts.'
            encoded_fromaddr, charset = decoded_fromaddr[0]
            if charset is not None:
                fromaddr = encoded_fromaddr.decode(charset)
        else:
            fromaddr = ''
        del message['X-Actually-From']

        toaddrs = message['X-Actually-To']
        if toaddrs is not None:
            decoded_toaddrs = header.decode_header(toaddrs)
            assert len(decoded_toaddrs) == 1, 'To header has multiple parts.'
            encoded_toaddrs, charset = decoded_toaddrs[0]
            if charset is not None:
                toaddrs = encoded_toaddrs.decode(charset)
            toaddrs = tuple(a.strip() for a in toaddrs.split(','))
        else:
            toaddrs = ()
        del message['X-Actually-To']

        return fromaddr, toaddrs, message

    def _send_message(self, filename):
        fromaddr = ''
        toaddrs = ()
        head, tail = os.path.split(filename)
        tmp_filename = os.path.join(head, '.sending-' + tail)
        rejected_filename = os.path.join(head, '.rejected-' + tail)
        try:
            # perform a series of operations in an attempt to ensure
            # that no two threads/processes send this message
            # simultaneously as well as attempting to not generate
            # spurious failure messages in the log; a diagram that
            # represents these operations is included in a
            # comment above this class
            try:
                # find the age of the tmp file (if it exists)
                mtime = os.stat(tmp_filename)[stat.ST_MTIME]
            except OSError:
                # BBB Python 2.5 compat
                e = sys.exc_info()[1]
                if e.errno == errno.ENOENT: # file does not exist
                    # the tmp file could not be stated because it
                    # doesn't exist, that's fine, keep going
                    age = None
                else: #pragma NO COVER
                    # the tmp file could not be stated for some reason
                    # other than not existing; we'll report the error
                    raise
            else:
                age = time.time() - mtime

            # if the tmp file exists, check it's age
            if age is not None:
                try:
                    if age > MAX_SEND_TIME:
                        # the tmp file is "too old"; this suggests
                        # that during an attemt to send it, the
                        # process died; remove the tmp file so we
                        # can try again
                        os.remove(tmp_filename)
                    else:
                        # the tmp file is "new", so someone else may
                        # be sending this message, try again later
                        return
                    # if we get here, the file existed, but was too
                    # old, so it was unlinked
                except OSError: #pragma NO COVER
                    # BBB Python 2.5 compat
                    e = sys.exc_info()[1]
                    if e.errno == errno.ENOENT: # file does not exist
                        # it looks like someone else removed the tmp
                        # file, that's fine, we'll try to deliver the
                        # message again later
                        return

            # now we know that the tmp file doesn't exist, we need to
            # "touch" the message before we create the tmp file so the
            # mtime will reflect the fact that the file is being
            # processed (there is a race here, but it's OK for two or
            # more processes to touch the file "simultaneously")
            try:
                os.utime(filename, None)
            except OSError: #pragma NO COVER
                # BBB Python 2.5 compat
                e = sys.exc_info()[1]
                if e.errno == errno.ENOENT: # file does not exist
                    # someone removed the message before we could
                    # touch it, no need to complain, we'll just keep
                    # going
                    return
                else:
                    # Some other error, propogate it
                    raise

            # creating this hard link will fail if another process is
            # also sending this message
            try:
                _os_link(filename, tmp_filename)
            except OSError: #pragma NO COVER
                # BBB Python 2.5 compat
                e = sys.exc_info()[1]
                if e.errno == errno.EEXIST: # file exists, *nix
                    # it looks like someone else is sending this
                    # message too; we'll try again later
                    return
                else:
                    # Some other error, propogate it
                    raise

            # FIXME: Need to test in Windows.  If
            # test_concurrent_delivery passes, this stanza can be
            # deleted.  Otherwise we probably need to catch
            # WindowsError and check for corresponding error code.
            #except error as e:
            #    if e[0] == 183 and e[1] == 'CreateHardLink':
            #        # file exists, win32
            #        return

            # read message file and send contents
            fromaddr, toaddrs, message = self._parseMessage(open(filename))
            try:
                self.mailer.send(fromaddr, toaddrs, message)
            except smtplib.SMTPResponseException:
                # BBB Python 2.5 compat
                e = sys.exc_info()[1]
                if 500 <= e.smtp_code <= 599:
                    # permanent error, ditch the message
                    self.log.error(
                        "Discarding email from %s to %s due to"
                        " a permanent error: %s",
                        fromaddr, ", ".join(toaddrs), e.args)
                    _os_link(filename, rejected_filename)
                else:
                    # Log an error and retry later
                    raise

            try:
                os.remove(filename)
            except OSError: #pragma NO COVER
                # BBB Python 2.5 compat
                e = sys.exc_info()[1]
                if e.errno == errno.ENOENT: # file does not exist
                    # someone else unlinked the file; oh well
                    pass
                else:
                    # something bad happend, log it
                    raise

            try:
                os.remove(tmp_filename)
            except OSError: #pragma NO COVER
                # BBB Python 2.5 compat
                e = sys.exc_info()[1]
                if e.errno == errno.ENOENT: # file does not exist
                    # someone else unlinked the file; oh well
                    pass
                else:
                    # something bad happened, log it
                    raise

            # TODO: maybe log the Message-Id of the message sent
            self.log.info("Mail from %s to %s sent.",
                          fromaddr, ", ".join(toaddrs))

        # Catch errors and log them here
        except:
            if fromaddr != '' or toaddrs != ():
                self.log.error(
                    "Error while sending mail from %s to %s.",
                    fromaddr, ", ".join(toaddrs), exc_info=True)
            else:
                self.log.error(
                    "Error while sending mail : %s ",
                    filename, exc_info=True)

class ConsoleApp(object):
    """Allows running of Queue Processor from the console.

    Currently this is hardcoded to use an SMTPMailer to deliver messages.  I am
    still contemplating what a better configuration story for this might be.

    """
    _usage = """%(script_name)s [OPTIONS] path/to/maildir

    OPTIONS:
        --hostname          Name of smtp host to use for delivery.  Default is
                            localhost.

        --port              Which port on smtp server to deliver mail to.
                            Default is 25.

        --username          Username to use to log in to smtp server.  Default
                            is none.

        --password          Password to use to log in to smtp server.  Must be
                            specified if username is specified.

        --force-tls         Do not connect if TLS is not available.  Not
                            enabled by default.

        --no-tls            Do not use TLS even if is available.  Not enabled
                            by default.

        --config <inifile>  Get configuration from specificed ini file.  Will
                            look for etc/qp.ini, by default, where etc is
                            parallel to the bin directory where the python
                            executable is found.  If this option is not
                            specified and etc/qp.ini is not in filesystem, no
                            config file will be read and default values will be
                            used for all options.

        --debug-smtp        Enable SMTP debug output (STDERR)
    """
    _error = False
    hostname = "localhost"
    port = 25
    username = None
    password = None
    force_tls = False
    no_tls = False
    queue_path = None
    debug_smtp = False

    def __init__(self, argv=sys.argv):
        self.script_name = argv[0]
        self._load_config()
        self._process_args(argv[1:])
        self.mailer = SMTPMailer(self.hostname,
                                 self.port,
                                 self.username,
                                 self.password,
                                 self.no_tls,
                                 self.force_tls,
                                 self.debug_smtp)
    def main(self):
        if self._error:
            return

        qp = QueueProcessor(self.mailer, self.queue_path)
        qp.send_messages()

    def _process_args(self, args):
        got_queue_path = False
        log_usage = False
        while args:
            arg = args.pop(0)
            if arg == "--hostname":
                if not args:
                    log_usage = True
                else:
                    self.hostname = args.pop(0)

            elif arg == "--port":
                try:
                    self.port = int(args.pop(0))
                except:
                    log_usage = True

            elif arg == "--username":
                if not args:
                    log_usage = True
                else:
                    self.username = args.pop(0)

            elif arg == "--password":
                if not args:
                    log_usage = True
                else:
                    self.password = args.pop(0)

            elif arg == "--force-tls":
                self.force_tls = True

            elif arg == "--no-tls":
                self.no_tls = True

            elif arg == "--config":
                if not args:
                    log_usage = True
                else:
                    self._load_config(args.pop(0))

            elif arg == "--debug-smtp":
                self.debug_smtp = True

            elif arg.startswith("-") or got_queue_path:
                log_usage = True

            else:
                self.queue_path = arg
                got_queue_path = True

        if not self.queue_path:
            log_usage = True

        if log_usage:
            self._error_usage()

        if ((self.username or self.password)
            and not (self.username and self.password)):
            _log_error("Must use username and password together.")
            self._error = True

        if self.force_tls and self.no_tls:
            _log_error("--force-tls and --no-tls are mutually exclusive.")
            self._error = True

    def _load_config(self, path=None):
        if path is None:
            # Look in etc directory relative to bin directory of current
            # Python executable for "qp.ini".
            exe = sys.executable
            root = os.path.dirname(os.path.dirname(exe))
            path = os.path.join(root, "etc", "qp.ini")
            if not os.path.exists(path):
                return

        section = "app:qp"
        names = [
            "hostname",
            "port",
            "username",
            "password",
            "force_tls",
            "no_tls",
            "queue_path",
            "debug_smtp",
        ]
        defaults = dict([(name, str(getattr(self, name))) for name in names])
        config = ConfigParser(defaults)
        config.read(path)

        self.hostname = config.get(section, "hostname")
        self.port = int(config.get(section, "port"))
        self.username = string_or_none(config.get(section, "username"))
        self.password = string_or_none(config.get(section, "password"))
        self.force_tls = boolean(config.get(section, "force_tls"))
        self.no_tls = boolean(config.get(section, "no_tls"))
        self.queue_path = string_or_none(config.get(section, "queue_path"))
        self.debug_smtp = string_or_none(config.get(section, "debug_smtp"))


    def _error_usage(self):
        _log_error(self._usage % {"script_name": self.script_name})
        self._error = True

def run_console(): #pragma NO COVERAGE
    logging.basicConfig()
    app = ConsoleApp()
    app.main()

if __name__ == "__main__": #pragma NO COVERAGE
    run_console()
