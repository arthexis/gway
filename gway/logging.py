# gway/logging.py

import os
import sys
import logging
import logging.handlers
import traceback
import random
import string

def _random_id(length=4):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

GWAY_LOG_ID = _random_id()

class FilteredFormatter(logging.Formatter):
    """
    Custom formatter:
    - Strips gway/gway frames if not debug.
    - Rewrites [gw] or [gw.something] as [gw:id] or [gw:id.something] in %(name)s for unique instance tagging.
    """
    def __init__(self, *args, debug=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.debug = debug

    def formatException(self, ei):
        exc_type, exc_value, tb = ei
        all_frames = traceback.extract_tb(tb)
        kept_frames = []
        skipped = 0

        for frame in all_frames:
            norm = frame.filename.replace('\\', '/')
            if '/gway/gway/' in norm and not self.debug:
                skipped += 1
            else:
                kept_frames.append(frame)

        formatted = []
        if kept_frames:
            formatted.extend(traceback.format_list(kept_frames))
        if skipped and not self.debug:
            formatted.append(f'  <... {skipped} frame(s) in gway internals skipped ...>\n')
        formatted.extend(traceback.format_exception_only(exc_type, exc_value))
        return ''.join(formatted)

    def format(self, record):
        # Patch logger name for gw loggers
        name = record.name
        if name == "gw":
            record.name = f"gw:{GWAY_LOG_ID}"
        elif name.startswith("gw."):
            record.name = f"gw:{GWAY_LOG_ID}" + name[2:]  # Keep module, replace only the prefix
        # else, leave as is for non-gw loggers
        return super().format(record)

def setup_logging(*,
                  logfile=None, logdir="logs", prog_name="gway", debug=False,
                  loglevel="INFO", pattern=None, backup_count=7,
                  verbose=False):
    """Globally configure logging with filtered tracebacks, unique log instance IDs, and library silencing."""
    loglevel = getattr(logging, str(loglevel).upper(), logging.INFO)

    if logfile:
        os.makedirs(logdir, exist_ok=True)
        if not os.path.isabs(logfile):
            logfile = os.path.join(os.getcwd(), logdir, logfile)

    # Replace [%(name)s] with [%(name)s] in pattern to allow the formatter to patch the name in-place
    pattern = pattern or '%(asctime)s %(levelname)s [%(name)s] %(filename)s:%(lineno)d @ %(funcName)s # %(message)s'

    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
    root.setLevel(loglevel)
    root.addHandler(logging.NullHandler())
    formatter = FilteredFormatter(pattern, datefmt='%H:%M:%S', debug=debug)

    if logfile:
        file_h = logging.handlers.TimedRotatingFileHandler(
            logfile, when='midnight', interval=1,
            backupCount=backup_count, encoding='utf-8'
        )
        file_h.setLevel(loglevel)
        file_h.setFormatter(formatter)
        root.addHandler(file_h)

    sep = "-" * len(' '.join(sys.argv[1:])) + "-------"
    cmd_args = " ".join(sys.argv[1:])
    root.info(f"\n\n> {prog_name} {cmd_args}\n{sep}")
    root.info(f"Loglevel set to {loglevel} ({logging.getLevelName(loglevel)}), log id: {GWAY_LOG_ID}")

    # Silencing non-gw loggers unless verbose is true
    if not verbose:
        manager = logging.Logger.manager
        for name, logger in manager.loggerDict.items():
            if name and not name.startswith("gw"):
                if isinstance(logger, logging.Logger):
                    logger.setLevel(logging.WARNING)
        # Patch getLogger for dynamic loggers
        _orig_getLogger = logging.getLogger
        def getLoggerPatched(name=None):
            logger = _orig_getLogger(name)
            if name and not name.startswith("gw"):
                logger.setLevel(logging.WARNING)
            return logger
        logging.getLogger = getLoggerPatched

    return root
