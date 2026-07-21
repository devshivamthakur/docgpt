import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.core.config import settings

logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, text_content: str, html_content: str = None) -> bool:
    """Send an email using standard library smtplib.
    
    If SMTP parameters are not set or sending fails, it logs the email to console/logs.
    """
    logger.info("Preparing to send email to %s: %s", to_email, subject)
    
    # Create message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM_EMAIL or "noreply@docgpt.com"
    msg["To"] = to_email

    # Record the MIME types of both parts - text/plain and text/html.
    part1 = MIMEText(text_content, "plain")
    msg.attach(part1)

    if html_content:
        part2 = MIMEText(html_content, "html")
        msg.attach(part2)

    # If SMTP_HOST is not set or SMTP credentials are missing in development, log the email and return True
    if not settings.SMTP_HOST or (not settings.SMTP_USER and settings.environment == "development"):
        logger.info("=== LOCAL DEVELOPMENT EMAIL EMULATION ===")
        logger.info("To: %s", to_email)
        logger.info("Subject: %s", subject)
        logger.info("Body (Text):\n%s", text_content)
        if html_content:
            logger.info("Body (HTML):\n%s", html_content[:500] + ("..." if len(html_content) > 500 else ""))
        logger.info("=========================================")
        return True

    try:
        # Determine whether to use TLS/SSL or plain
        if settings.SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10)
            if settings.SMTP_PORT == 587:
                server.starttls()
        
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            
        server.sendmail(msg["From"], [to_email], msg.as_string())
        server.quit()
        logger.info("Email sent successfully to %s", to_email)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s via SMTP: %s", to_email, str(e))
        logger.info("=== FALLBACK EMAIL LOGGING ===")
        logger.info("To: %s", to_email)
        logger.info("Subject: %s", subject)
        logger.info("Body (Text):\n%s", text_content)
        logger.info("==============================")
        return False
