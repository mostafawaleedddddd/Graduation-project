import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

SENDER_EMAIL = "wmostafa392@gmail.com"
SENDER_PASSWORD = "xxoj vdbx hpcg kdiu"


def send_email(subject, body, image_bytes=None, image_filename="detected_frame.jpg",
               receiver_email=None):
    """
    Send an email alert.

    receiver_email: Must be supplied. No hardcoded fallback recipient is used.
    """
    if not receiver_email:
        print("❌ No receiver email provided. Email not sent.")
        return False

    to_addr = receiver_email

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"]   = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if image_bytes is not None:
        image_part = MIMEImage(image_bytes, _subtype="jpeg")
        image_part.add_header(
            "Content-Disposition",
            "attachment",
            filename=image_filename,
        )
        msg.attach(image_part)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, to_addr, msg.as_string())
        print(f"✅ Email sent successfully to {to_addr}")
        return True
    except Exception as exc:
        print(f"❌ Failed to send email: {exc}")
        return False