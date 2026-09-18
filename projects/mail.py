
# projects/mail.py

import os
from gway import gw
import imaplib
import smtplib
import asyncio
import threading
import contextlib
from datetime import date, datetime
from email.mime.text import MIMEText
from email import message_from_bytes


def _escape_imap_string(value: str) -> str:
    """Escape backslashes and quotes for IMAP SEARCH."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _format_imap_date(value):
    """Return date in IMAP DD-Mon-YYYY format."""
    if isinstance(value, (datetime, date)):
        return value.strftime('%d-%b-%Y')
    return str(value)


def send(subject, body=None, to=None, threaded=None, **kwargs):
    """
    Send an email with the specified subject and body, using defaults from env if available.

    Parameters:
    - subject: the email subject (string)
    - body:    the plain-text body (string). Must be provided.
    - to:      recipient address (string). Defaults to ADMIN_EMAIL from the environment.
    - threaded:  if True, send the email asynchronously; if False, block and send; if None, auto-detect.
    - **kwargs: reserved for future use.

    Returns:
        str ("Email sent successfully to ...") or error message, unless threaded is True (returns immediately).
    """

    def _send_email():
        _to = to or os.environ.get("ADMIN_EMAIL")
        if not body:
            gw.debug("No email body provided.")
            return "No email body provided."

        gw.debug(f"Preparing to send email to {_to}: {subject}")

        # Load SMTP configuration from environment
        sender_email    = os.environ.get("MAIL_SENDER")
        sender_password = os.environ.get("MAIL_PASSWORD")
        smtp_server     = os.environ.get("SMTP_SERVER")
        smtp_port       = os.environ.get("SMTP_PORT")

        gw.debug(f"MAIL_SENDER: {sender_email}")
        gw.debug(f"SMTP_SERVER: {smtp_server}")
        gw.debug(f"SMTP_PORT: {smtp_port}")
        gw.debug("Environment variables loaded.")

        # If any required piece is missing, bail out
        if not all([sender_email, sender_password, smtp_server, smtp_port]):
            gw.debug("Missing one or more required email configuration details.")
            return "Missing email configuration details."

        # Construct the MIMEText message with explicit UTF-8 encoding
        msg = MIMEText(body, _charset="utf-8")
        msg['Subject'] = gw.resolve(subject)
        msg['From']    = sender_email
        msg['To']      = _to

        gw.debug("Email MIME message constructed.")
        gw.debug(f"Email headers: From={msg['From']}, To={msg['To']}, Subject={msg['Subject']}")

        try:
            gw.debug(f"Connecting to SMTP server: {smtp_server}:{smtp_port}")
            server = smtplib.SMTP(smtp_server, int(smtp_port))
            gw.debug("SMTP connection established. Starting TLS...")
            server.starttls()
            gw.debug("TLS started. Logging in...")  
            server.login(sender_email, sender_password)
            gw.debug("Login successful. Sending message...")
            server.send_message(msg)
            server.quit()
            gw.debug("Email sent and SMTP session closed.")
            return "Email sent successfully to " + _to
        except Exception as e:
            gw.debug(f"Exception occurred while sending email: {e}")
            return f"Error sending email: {e}"

    # Auto-detect async mode if not specified
    if threaded is None:
        try:
            asyncio.get_running_loop()
            threaded = True
        except RuntimeError:
            threaded = False

    if threaded:
        try:
            loop = asyncio.get_running_loop()
            async def async_task():
                result = await asyncio.to_thread(_send_email)
                if result and "Error" in result:
                    gw.error(result)
            asyncio.create_task(async_task())
        except RuntimeError:
            def thread_task():
                result = _send_email()
                if result and "Error" in result:
                    gw.error(result)
            threading.Thread(target=thread_task, daemon=True).start()
        return "Email send scheduled (async mode)"
    else:
        return _send_email()


def read(subject_fragment, body_fragment=None, sender=None, since=None, before=None):
    """Read the most recent email matching criteria.

    Parameters
    ----------
    subject_fragment : str
        Fragment of the subject to search for. Use "*" to match any subject.
    body_fragment : str, optional
        Text to search for within the body.
    sender : str, optional
        Limit results to emails from this sender.
    since : str or :class:`datetime.date`, optional
        Only return messages on or after this date.
    before : str or :class:`datetime.date`, optional
        Only return messages before this date.
    """
    EMAIL_SENDER = os.environ.get("MAIL_SENDER")
    EMAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    IMAP_SERVER = os.environ.get("IMAP_SERVER")
    IMAP_PORT = os.environ.get("IMAP_PORT")

    if not all([EMAIL_SENDER, EMAIL_PASSWORD, IMAP_SERVER, IMAP_PORT]):
        raise RuntimeError(
            "Missing email configuration: MAIL_SENDER, MAIL_PASSWORD, IMAP_SERVER, IMAP_PORT"
        )

    mail = None
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_SENDER, EMAIL_PASSWORD)
        # Try to enable UTF-8 mode if the server supports it
        try:
            mail.enable('UTF8=ACCEPT')
        except Exception:
            pass
        # Ensure mailbox is selected case-sensitively for broader compatibility
        mail.select('INBOX')

        criteria = []
        if subject_fragment and subject_fragment != "*":
            esc_subject = _escape_imap_string(subject_fragment)
            criteria.extend(["SUBJECT", f'"{esc_subject}"'])
        if body_fragment:
            esc_body = _escape_imap_string(body_fragment)
            criteria.extend(["BODY", f'"{esc_body}"'])
        if sender:
            esc_sender = _escape_imap_string(sender)
            criteria.extend(["FROM", f'"{esc_sender}"'])
        if since:
            criteria.extend(["SINCE", _format_imap_date(since)])
        if before:
            criteria.extend(["BEFORE", _format_imap_date(before)])

        if not criteria:
            gw.warning("No search criteria provided.")
            return None

        try:
            if getattr(mail, 'utf8_enabled', False):
                status, data = mail.search(None, *criteria)
            else:
                encoded_criteria = [
                    c.encode('utf-8') if isinstance(c, str) else c
                    for c in criteria
                ]
                try:
                    status, data = mail.search('UTF-8', *encoded_criteria)
                except imaplib.IMAP4.error as e:
                    if 'bad' in str(e).lower() or 'parse' in str(e).lower():
                        gw.warning(
                            f"Search charset failed ({e}); retrying without charset"
                        )
                        status, data = mail.search(None, *encoded_criteria)
                    else:
                        raise
        except imaplib.IMAP4.error as e:
            raise
        mail_ids = data[0].split()

        if not mail_ids:
            gw.warning("No emails found with the specified criteria.")
            return None

        latest_mail_id = mail_ids[-1]
        status, data = mail.fetch(latest_mail_id, '(RFC822)')
        email_msg = message_from_bytes(data[0][1])

        gw.info(f"Fetching email with ID {latest_mail_id}")

        attachments = []
        email_content = None

        if email_msg.is_multipart():
            for part in email_msg.walk():
                content_type = part.get_content_type()
                if content_type in ["text/plain", "text/html"]:
                    email_content = part.get_payload(decode=True).decode()
                elif part.get('Content-Disposition') is not None:
                    file_data = part.get_payload(decode=True)
                    file_name = part.get_filename()
                    attachments.append((file_name, file_data))

        elif email_msg.get_content_type() in ["text/plain", "text/html"]:
            email_content = email_msg.get_payload(decode=True).decode()

        if not email_content:
            gw.warning("Matching email found, but unsupported content type.")
            return None

        return email_content, attachments

    except Exception as e:
        gw.error(f"Error reading email: {str(e)}")
        raise

    finally:
        if mail:
            with contextlib.suppress(imaplib.IMAP4.error):
                mail.close()
            with contextlib.suppress(Exception):
                mail.logout()


def search(subject_fragment="*", body_fragment=None, sender=None, to=None, since=None, before=None, limit=10, reverse=False):
    """Search for emails and return summaries (subject, date, sender).

    Parameters
    ----------
    subject_fragment : str
        Part of the subject to match. ``"*"`` matches any subject.
    body_fragment : str, optional
        Text to search for in the body.
    sender : str, optional
        Only return messages from this sender.
    to : str or bool, optional
        Filter by destination address. If ``True`` use ``ADMIN_EMAIL`` from the
        environment.
    since : str or :class:`datetime.date`, optional
        Only return messages on or after this date.
    before : str or :class:`datetime.date`, optional
        Only return messages before this date.
    limit : int, optional
        Maximum number of results to return. ``None`` returns all. Defaults to
        ``10``.
    reverse : bool, optional
        If ``True`` return results from oldest to newest instead of newest to
        oldest.
    """
    EMAIL_SENDER = os.environ.get("MAIL_SENDER")
    EMAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    IMAP_SERVER = os.environ.get("IMAP_SERVER")
    IMAP_PORT = os.environ.get("IMAP_PORT")

    if not all([EMAIL_SENDER, EMAIL_PASSWORD, IMAP_SERVER, IMAP_PORT]):
        raise RuntimeError(
            "Missing email configuration: MAIL_SENDER, MAIL_PASSWORD, IMAP_SERVER, IMAP_PORT"
        )

    mail = None
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_SENDER, EMAIL_PASSWORD)
        try:
            mail.enable('UTF8=ACCEPT')
        except Exception:
            pass
        mail.select('INBOX')

        criteria = []
        if subject_fragment and subject_fragment != "*":
            esc_subject = _escape_imap_string(subject_fragment)
            criteria.extend(["SUBJECT", f'"{esc_subject}"'])
        if body_fragment:
            esc_body = _escape_imap_string(body_fragment)
            criteria.extend(["BODY", f'"{esc_body}"'])
        if sender:
            esc_sender = _escape_imap_string(sender)
            criteria.extend(["FROM", f'"{esc_sender}"'])
        if to is True:
            to = os.environ.get("ADMIN_EMAIL")
        if to:
            esc_to = _escape_imap_string(to)
            criteria.extend(["TO", f'"{esc_to}"'])
        if since:
            criteria.extend(["SINCE", _format_imap_date(since)])
        if before:
            criteria.extend(["BEFORE", _format_imap_date(before)])

        if not criteria:
            gw.warning("No search criteria provided.")
            return []

        if getattr(mail, 'utf8_enabled', False):
            status, data = mail.search(None, *criteria)
        else:
            encoded_criteria = [c.encode('utf-8') if isinstance(c, str) else c for c in criteria]
            try:
                status, data = mail.search('UTF-8', *encoded_criteria)
            except imaplib.IMAP4.error as e:
                if 'bad' in str(e).lower() or 'parse' in str(e).lower():
                    gw.warning(f"Search charset failed ({e}); retrying without charset")
                    status, data = mail.search(None, *encoded_criteria)
                else:
                    raise

        mail_ids = data[0].split()
        results = []
        for m_id in mail_ids:
            status, fdata = mail.fetch(m_id, '(RFC822)')
            email_msg = message_from_bytes(fdata[0][1])
            results.append({
                'subject': email_msg.get('Subject'),
                'from': email_msg.get('From'),
                'date': email_msg.get('Date'),
            })

        try:
            from email.utils import parsedate_to_datetime
            def _date_key(item):
                try:
                    return parsedate_to_datetime(item.get('date'))
                except Exception:
                    return datetime.min
            results.sort(key=_date_key, reverse=not reverse)
        except Exception:
            pass

        if limit is not None:
            results = results[:limit]

        return results

    except Exception as e:
        gw.error(f"Error searching email summaries: {str(e)}")
        raise
    finally:
        if mail:
            with contextlib.suppress(imaplib.IMAP4.error):
                mail.close()
            with contextlib.suppress(Exception):
                mail.logout()

