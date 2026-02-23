import sys

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Send a smoke-test email through the app SMTP stack to verify delivery."

    def add_arguments(self, parser):
        parser.add_argument("--to", required=True, help="Recipient email address")
        parser.add_argument("--subject", default="LearnPuddle SMTP Smoke Test")
        parser.add_argument("--body", default="")

    def handle(self, *args, **options):
        to = options["to"]
        subject = options["subject"]
        body = options["body"] or (
            "This is a smoke-test email sent from the LearnPuddle platform.\n\n"
            "If you received this, SMTP delivery is working correctly.\n\n"
            f"— {getattr(settings, 'PLATFORM_NAME', 'LearnPuddle')}"
        )
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@learnpuddle.com")

        self.stdout.write(f"SMTP config:")
        self.stdout.write(f"  HOST     = {settings.EMAIL_HOST}")
        self.stdout.write(f"  PORT     = {settings.EMAIL_PORT}")
        self.stdout.write(f"  TLS      = {settings.EMAIL_USE_TLS}")
        self.stdout.write(f"  SSL      = {getattr(settings, 'EMAIL_USE_SSL', False)}")
        self.stdout.write(f"  USER     = {settings.EMAIL_HOST_USER}")
        self.stdout.write(f"  FROM     = {from_email}")
        self.stdout.write(f"  TO       = {to}")
        self.stdout.write(f"  SUBJECT  = {subject}")
        self.stdout.write("")

        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=from_email,
                recipient_list=[to],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS(f"Email sent successfully to {to}"))
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Email send FAILED: {exc}"))
            sys.exit(1)
