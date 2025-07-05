# TODO: Use the mail project to create a simple approval request workflow

# projects/mail.py

import os
from gway import gw
import imaplib
import smtplib
import asyncio
import threading
from email.mime.text import MIMEText
from email import message_from_bytes


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

        # Construct the MIMEText message
        msg = MIMEText(body)
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


def search(subject_fragment, body_fragment=None):
    """
    Search emails by subject and optionally body. Use "*" to match any subject.
    """
    EMAIL_SENDER = os.environ["MAIL_SENDER"]
    EMAIL_PASSWORD = os.environ["MAIL_PASSWORD"]
    IMAP_SERVER = os.environ["IMAP_SERVER"]
    IMAP_PORT = os.environ["IMAP_PORT"]

    mail = None
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(EMAIL_SENDER, EMAIL_PASSWORD)
        # Try to enable UTF-8 mode if the server supports it
        try:
            mail.enable('UTF8=ACCEPT')
        except Exception:
            pass
        mail.select('inbox')

        search_criteria = []
        if subject_fragment and subject_fragment != "*":
            search_criteria.append(f'(SUBJECT "{subject_fragment}")')
        if body_fragment:
            search_criteria.append(f'(BODY "{body_fragment}")')

        if not search_criteria:
            gw.warning("No search criteria provided.")
            return None

        combined_criteria = ' '.join(search_criteria)

        try:
            if getattr(mail, 'utf8_enabled', False):
                status, data = mail.search(None, combined_criteria)
            else:
                status, data = mail.search('UTF-8', combined_criteria.encode('utf-8'))
        except imaplib.IMAP4.error as e:
            if 'bad' in str(e).lower() or 'parse' in str(e).lower():
                gw.warning(f"Search charset failed ({e}); retrying without charset")
                status, data = mail.search(None, combined_criteria)
            else:
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
        gw.error(f"Error searching email: {str(e)}")
        raise

    finally:
        if mail:
            mail.close()
            mail.logout()

