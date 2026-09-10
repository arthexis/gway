from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Echo one integer for GWAY chain transfer tests."

    def add_arguments(self, parser):
        parser.add_argument("value", type=int)

    def handle(self, *args, **options):
        self.stdout.write(str(options["value"]))
