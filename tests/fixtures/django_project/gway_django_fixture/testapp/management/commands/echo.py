from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Echo one value for GWAY adapter integration tests."

    def add_arguments(self, parser):
        parser.add_argument("value")

    def handle(self, *args, **options):
        del args
        self.stdout.write(options["value"])
