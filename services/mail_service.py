"""Outbox persistente, executada fora dos processos web. Envio real opt-in."""
from email.message import EmailMessage
import os
import smtplib
import ssl
import time
from .enterprise_service import stamp


def smtp_send(recipient, subject, body):
    host = os.environ['DASHBOARD_SMTP_HOST']
    sender = os.environ['DASHBOARD_MAIL_FROM']
    message = EmailMessage()
    message['From'] = sender
    message['To'] = recipient
    message['Subject'] = subject
    message.set_content(body)
    # TLS obrigatório; nunca trafegar credenciais em conexão aberta.
    with smtplib.SMTP(host, int(os.environ.get('DASHBOARD_SMTP_PORT', '587')), timeout=20) as client:
        client.starttls(context=ssl.create_default_context())
        if os.environ.get('DASHBOARD_SMTP_USER'):
            client.login(os.environ['DASHBOARD_SMTP_USER'], os.environ['DASHBOARD_SMTP_PASSWORD'])
        client.send_message(message)


def process_outbox(auth, sender=None, limit=25):
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
            db.execute("UPDATE outbox SET status='sending',attempts=attempts+1 WHERE id=?", (row['id'],))
            attempt_id = db.execute("INSERT INTO mail_attempts(outbox_id,occurred,result) VALUES (?,?,'sending')", (row['id'], stamp())).lastrowid
        try:
            sender(row['recipient'], row['subject'], row['body'])
        except Exception as error:
            # Only class name: no provider text, addresses, tokens or credentials.
            attempts = row['attempts'] + 1
            ambiguous = isinstance(error, (smtplib.SMTPServerDisconnected, TimeoutError))
            with auth.connect() as db:
                status = 'uncertain' if ambiguous else ('failed' if attempts >= 3 else 'pending')
                db.execute('UPDATE outbox SET status=?,next_attempt=?,last_error=? WHERE id=?', (status, time.time() + 60 * 2 ** attempts, type(error).__name__, row['id']))
                db.execute('UPDATE mail_attempts SET result=?,error_type=? WHERE id=?', (status, type(error).__name__, attempt_id))
        else:
            with auth.connect() as db:
                db.execute("UPDATE outbox SET status='sent',last_error=NULL WHERE id=?", (row['id'],))
                db.execute("UPDATE mail_attempts SET result='sent' WHERE id=?", (attempt_id,))
            delivered += 1
    return delivered
