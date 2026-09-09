from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Write a result before exiting with failure"

    def handle(self, *args, **options):
        self.stdout.write("FAIL")
        raise SystemExit(1)
