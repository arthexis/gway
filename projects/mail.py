# projects/mail.py

import os
from gway import gw
import imaplib
import smtplib
from email.mime.text import MIMEText
from email import message_from_bytes


def send(subject, body=None, to=None, **kwargs):
    """
    Send an email with the specified subject and body, using defaults from env if available.
    If body is None, send system info and recent logs (via gw.node.report(**kwargs)).
    
    Parameters:
    - subject: the email subject (string)
    - body:    the plain-text body (string). If omitted, gw.node.report(**kwargs) will be used.
    - to:      recipient address (string). Defaults to ADMIN_EMAIL from the environment.
    - **kwargs: passed into gw.node.report() when body is None.
    """
    # Determine recipient
    to = to or os.environ.get("ADMIN_EMAIL")
    gw.debug(f"Preparing to send email to {to}: {subject}")

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

    # If no explicit body was passed, ask gw.node.report() to build one
    if body is None:
        body = gw.node.report(**kwargs)

    # Construct the MIMEText message
    msg = MIMEText(body)
    msg['Subject'] = gw.resolve(subject)
    msg['From']    = sender_email
    
    msg['To']      = to

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
        return "Email sent successfully to " + to
    except Exception as e:
        gw.debug(f"Exception occurred while sending email: {e}")
        return f"Error sending email: {e}"


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
        status, data = mail.search(None, combined_criteria)
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
