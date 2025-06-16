# gway/logging.py

# Avoid using Gateway here at all, if it fails here we won't get any logging!

import os
import sys
import logging
import logging.handlers
import traceback
import random
import string
import threading
from contextlib import contextmanager

def _random_id(length=4):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

GWAY_LOG_ID = _random_id()

def _get_thread_shortid():
    # Uses 4 most significant hex digits of thread id (zero-padded)
    tid = threading.get_ident()
    return f"{tid:0>4x}"[-4:]

# ---- Store config as globals ----
_last_logging_config = {}

def _save_config(config):
    global _last_logging_config
    _last_logging_config = config.copy()

def _get_last_config():
    return _last_logging_config.copy()

class FilteredFormatter(logging.Formatter):
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
        name = record.name
        thread_shortid = _get_thread_shortid()
        if name == "gw":
            record.name = f"gw:{GWAY_LOG_ID}:{thread_shortid}"
        elif name.startswith("gw."):
            record.name = f"gw:{GWAY_LOG_ID}:{thread_shortid}" + name[2:]
        else:
            # Leave non-gw loggers as is
            pass
        return super().format(record)

def setup_logging(*,
                  logfile=None, logdir="logs", prog_name="gway", debug=False,
                  loglevel="INFO", pattern=None, backup_count=7,
                  verbose=False):
    """Globally configure logging, and remember config for restoration."""
    loglevel = getattr(logging, str(loglevel).upper(), logging.INFO)

    if logfile:
        os.makedirs(logdir, exist_ok=True)
        if not os.path.isabs(logfile):
            logfile = os.path.join(os.getcwd(), logdir, logfile)

    pattern = pattern or '%(asctime)s %(levelname)s [%(name)s] %(funcName)s @ %(filename)s:%(lineno)d  # %(message)s '

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
        _orig_getLogger = logging.getLogger
        def getLoggerPatched(name=None):
            logger = _orig_getLogger(name)
            if name and not name.startswith("gw"):
                logger.setLevel(logging.WARNING)
            return logger
        logging.getLogger = getLoggerPatched

    # ---- Save config for restoration ----
    _save_config(dict(
        logfile=logfile, logdir=logdir, prog_name=prog_name, debug=debug,
        loglevel=loglevel, pattern=pattern, backup_count=backup_count, verbose=verbose
    ))

    return root

@contextmanager
def use_logging(**new_config):
    """
    Context manager: temporarily switch logging config, then restore previous.
    Usage:
        with use_logging(logfile="test.log", loglevel="DEBUG"):
            ...  # code here logs to test.log
        # after, logs restore to previous config
    """
    prev_config = _get_last_config()
    try:
        setup_logging(**new_config)
        yield
    finally:
        if prev_config:
            setup_logging(**prev_config)
