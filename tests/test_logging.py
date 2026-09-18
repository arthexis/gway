import os
import unittest
import tempfile
import logging
import traceback
from gway import logging as gway_logging
import unittest.mock


class LoggingSetupTests(unittest.TestCase):

    def setUp(self):
        self.tempfile = tempfile.NamedTemporaryFile(delete=False, suffix=".log")
        self.logfile_path = self.tempfile.name
        self.tempfile.close()

    def tearDown(self):
        # Close all handlers before deleting the file
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.flush()
            handler.close()
            root_logger.removeHandler(handler)
        if os.path.exists(self.logfile_path):
            os.remove(self.logfile_path)

    def test_logfile_creation_and_message(self):
        logger = gway_logging.setup_logging(logfile=os.path.basename(self.logfile_path), logdir=os.path.dirname(self.logfile_path), loglevel="INFO")
        logger.info("Test message")
        with open(self.logfile_path) as f:
            contents = f.read()
        self.assertIn("Test message", contents)

    def test_log_level_setting(self):
        logger = gway_logging.setup_logging(logfile=os.path.basename(self.logfile_path), logdir=os.path.dirname(self.logfile_path), loglevel="WARNING")
        self.assertEqual(logger.level, logging.WARNING)

    def test_custom_format_pattern(self):
        pattern = "%(levelname)s: %(message)s"
        logger = gway_logging.setup_logging(logfile=os.path.basename(self.logfile_path), logdir=os.path.dirname(self.logfile_path), loglevel="ERROR", pattern=pattern)
        logger.error("Formatted test")
        with open(self.logfile_path) as f:
            content = f.read()
        self.assertIn("ERROR: Formatted test", content)

    def test_formatter_skips_internal_frames(self):
        formatter = gway_logging.FilteredFormatter()

        import types
        fake_tb = types.SimpleNamespace(tb_next=None)
        gway_frame = traceback.FrameSummary("/usr/lib/gway/gway/core.py", 42, "inner")
        user_frame = traceback.FrameSummary("/project/main.py", 10, "user")

        with unittest.mock.patch("traceback.extract_tb", return_value=[gway_frame, user_frame]):
            result = formatter.formatException((ValueError, ValueError("dummy"), fake_tb))

        self.assertIn("frame(s) in gway internals skipped", result)


if __name__ == '__main__':
    unittest.main()
