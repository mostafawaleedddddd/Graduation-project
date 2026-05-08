import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

SENDER_EMAIL = "wmostafa392@gmail.com"
SENDER_PASSWORD = "xxoj vdbx hpcg kdiu"
RECEIVER_EMAIL = "mostafa2208461@miuegypt.edu.eg"


def send_email(subject, body, image_bytes=None, image_filename="detected_frame.jpg"):
    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
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
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("Email sent successfully!")
        return True
    except Exception as exc:
        print(f"Failed to send email: {exc}")
        return False
