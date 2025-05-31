import os
from gway import gw


def send(*, subject, message=None, to=None):
    """
    Send an email with the specified subject and message, using defaults from env if available.
    """
    import smtplib
    from email.mime.text import MIMEText

    to = to or os.environ.get("ADMIN_EMAIL")
    gw.debug(f"Preparing to send email to {to}: {subject}")

    # Retrieve default values from environment variables
    sender_email = os.environ.get("MAIL_SENDER", None)
    sender_password = os.environ.get("MAIL_PASSWORD", None)
    smtp_server = os.environ.get("SMTP_SERVER", None)
    smtp_port = os.environ.get("SMTP_PORT", None)

    gw.debug(f"MAIL_SENDER: {sender_email}")
    gw.debug(f"SMTP_SERVER: {smtp_server}")
    gw.debug(f"SMTP_PORT: {smtp_port}")
    gw.debug("Environment variables loaded.")

    # Ensure all required values are available
    if not all([sender_email, sender_password, smtp_server, smtp_port]):
        gw.debug("Missing one or more required email configuration details.")
        return "Missing email configuration details."

    # Create the email message
    msg = MIMEText(message)
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = to

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
