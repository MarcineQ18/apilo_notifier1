import smtplib
from email.message import EmailMessage

class Mailer:
    def __init__(self, host: str, port: int, user: str, password: str, mail_from: str):
        self.host = host
        self.port = int(port)
        self.user = user
        self.password = password
        self.mail_from = mail_from

    def send(self, to_addr: str, subject: str, body: str, is_html: bool = False) -> None:
        if not (self.host and self.port and self.user and self.password and self.mail_from):
            raise RuntimeError("Brakuje ustawień SMTP (HOST/PORT/USER/PASS/MAIL_FROM).")

        msg = EmailMessage()
        msg["From"] = self.mail_from
        msg["To"] = to_addr
        msg["Subject"] = subject

        if is_html:
            msg.set_content("Twoja poczta nie obsługuje HTML.")
            msg.add_alternative(body, subtype="html")
        else:
            msg.set_content(body)

        if self.port == 465:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=60) as server:
                server.login(self.user, self.password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=60) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self.user, self.password)
                server.send_message(msg)
