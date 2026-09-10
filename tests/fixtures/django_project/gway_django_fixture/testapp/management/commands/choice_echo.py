from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Echo one constrained value for GWAY chain transfer tests."

    def add_arguments(self, parser):
        parser.add_argument("value", choices=("ready", "waiting"))

    def handle(self, *args, **options):
        self.stdout.write(options["value"])
