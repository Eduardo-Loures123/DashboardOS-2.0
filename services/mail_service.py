"""Outbox persistente, executada fora dos processos web. Envio real opt-in."""
from email.message import EmailMessage
import os
import logging
import smtplib
import ssl
import time
from .enterprise_service import stamp

logger = logging.getLogger(__name__)


class SMTPTransportError(Exception):
    """Safe transport metadata; never persist the provider's response text."""
    def __init__(self, stage, error):
        self.stage = stage
        self.error_type = type(error).__name__
        code = getattr(error, 'smtp_code', None)
        self.smtp_code = code if isinstance(code, int) else None
        if isinstance(error, smtplib.SMTPRecipientsRefused):
            codes = [reply[0] for reply in error.recipients.values()]
            self.smtp_code = codes[0] if len(codes) == 1 and isinstance(codes[0], int) else None
        # An explicit rejection confirms non-acceptance. A lost DATA reply does not.
        rejected = isinstance(error, (smtplib.SMTPResponseException, smtplib.SMTPRecipientsRefused))
        self.uncertain = stage == 'TRANSMIT' and not rejected
        self.permanent = (isinstance(error, (RuntimeError, ValueError, ssl.SSLCertVerificationError,
                                            smtplib.SMTPNotSupportedError))
                          or self.smtp_code is not None and 500 <= self.smtp_code < 600)
        super().__init__('SMTP transport failed; safe metadata only.')


def _diagnostic(stage, result, error=None):
    log = logger.warning if error else logger.info
    log('smtp stage=%s result=%s error_type=%s smtp_code=%s', stage, result,
                error.error_type if error else None, error.smtp_code if error else None)


def email_suspended():
    """Release operacional: ausencia de opt-in bloqueia toda entrega legada."""
    return os.environ.get("DASHBOARD_EMAIL_SUSPENDED", "true").strip().lower() != "false"


def mail_configuration():
    missing = [key for key in ('DASHBOARD_SMTP_HOST', 'DASHBOARD_MAIL_FROM') if not os.environ.get(key)]
    if os.environ.get('DASHBOARD_SMTP_USER') and not os.environ.get('DASHBOARD_SMTP_PASSWORD'):
        missing.append('DASHBOARD_SMTP_PASSWORD')
    enabled = not email_suspended() and os.environ.get('DASHBOARD_MAIL_ENABLED') == 'true'
    return {'enabled': enabled, 'ready': enabled and not missing, 'missing': missing}


def smtp_send(recipient, subject, body):
    if not mail_configuration()['ready']:
        raise RuntimeError('Configuração de e-mail incompleta.')
    host = os.environ['DASHBOARD_SMTP_HOST']
    sender = os.environ['DASHBOARD_MAIL_FROM']
    message = EmailMessage()
    message['From'] = sender
    message['To'] = recipient
    message['Subject'] = subject
    message.set_content(body)
    # Explicit lifecycle: QUIT must never undo confirmed DATA acceptance.
    client = None
    stage = 'CONNECT'
    accepted = False
    try:
        client = smtplib.SMTP(host, int(os.environ.get('DASHBOARD_SMTP_PORT', '587')), timeout=20)
        stage = 'STARTTLS'
        client.starttls(context=ssl.create_default_context())
        stage = 'AUTH'
        if os.environ.get('DASHBOARD_SMTP_USER'):
            client.login(os.environ['DASHBOARD_SMTP_USER'], os.environ['DASHBOARD_SMTP_PASSWORD'])
        stage = 'TRANSMIT'
        # Exactly one envelope recipient: normal return confirms final DATA acceptance.
        refused = client.send_message(message, from_addr=sender, to_addrs=[recipient])
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)
        accepted = True
        _diagnostic(stage, 'accepted')
    except Exception as error:
        failure = SMTPTransportError(stage, error)
        _diagnostic(stage, 'uncertain' if failure.uncertain else 'not_accepted', failure)
        raise failure from None
    finally:
        if client is not None:
            try:
                if accepted:
                    code, _ = client.quit()
                    if code != 221:
                        raise smtplib.SMTPResponseException(code, b'')
            except Exception as error:
                _diagnostic('CLOSE', 'accepted_close_error', SMTPTransportError('CLOSE', error))
            finally:
                try:
                    client.close()
                except Exception as error:
                    _diagnostic('CLOSE', 'accepted_close_error' if accepted else 'close_error',
                                SMTPTransportError('CLOSE', error))


def process_outbox(auth, sender=None, limit=25):
    if email_suspended():
        return 0  # Antes de abrir SQLite ou selecionar/alterar qualquer mensagem.
    if sender is None and os.environ.get('DASHBOARD_MAIL_ENABLED') != 'true':
        return 0
    sender = sender or smtp_send
    delivered = 0
    # SQLite write lock serializes overlapping workers. Crash during SMTP can be
    # ambiguous: never automatically resend a 'sending' row (operator reviews it).
    for _ in range(limit):
        with auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT o.* FROM outbox o JOIN account a ON a.user_id=o.user_id WHERE o.status='pending' AND o.next_attempt<=? AND a.state='active' ORDER BY o.id LIMIT 1", (time.time(),)).fetchone()
            if not row:
                break
            account = db.execute('SELECT * FROM account WHERE user_id=?', (row['user_id'],)).fetchone()
            if row['recipient'] != account['email'] or (row['event_id'] is not None and (not account['verified'] or not account['email_alerts'])):
                db.execute("UPDATE outbox SET status='cancelled' WHERE id=?", (row['id'],))
                continue
            if row['event_id'] is None:
                raw = row['body'].rsplit(': ', 1)[-1]
                token = db.execute("SELECT 1 FROM tokens WHERE digest=? AND user_id=? AND purpose='verify' AND value=? AND expires>?", (auth.digest(raw), row['user_id'], row['recipient'], time.time())).fetchone()
                if not token or account['verified']:
                    db.execute("UPDATE outbox SET status='cancelled',body='' WHERE id=?", (row['id'],))
                    continue
            db.execute("UPDATE outbox SET status='sending',attempts=attempts+1 WHERE id=?", (row['id'],))
            attempt_id = db.execute("INSERT INTO mail_attempts(outbox_id,occurred,result) VALUES (?,?,'sending')", (row['id'], stamp())).lastrowid
        try:
            sender(row['recipient'], row['subject'], row['body'])
        except Exception as error:
            # Only class name: no provider text, addresses, tokens or credentials.
            attempts = row['attempts'] + 1
            transport = isinstance(error, SMTPTransportError)
            error_type = error.error_type if transport else type(error).__name__
            ambiguous = error.uncertain if transport else isinstance(error, (smtplib.SMTPServerDisconnected, TimeoutError))
            with auth.connect() as db:
                permanent = error.permanent if transport else isinstance(error, (smtplib.SMTPAuthenticationError, RuntimeError))
                status = 'uncertain' if ambiguous else ('failed' if permanent or attempts >= 3 else 'pending')
                db.execute('UPDATE outbox SET status=?,next_attempt=?,last_error=? WHERE id=?', (status, time.time() + 60 * 2 ** attempts, error_type, row['id']))
                db.execute('UPDATE mail_attempts SET result=?,error_type=? WHERE id=?', (status, error_type, attempt_id))
        else:
            with auth.connect() as db:
                db.execute("UPDATE outbox SET status='sent',last_error=NULL WHERE id=?", (row['id'],))
                db.execute("UPDATE mail_attempts SET result='sent' WHERE id=?", (attempt_id,))
            delivered += 1
    return delivered
