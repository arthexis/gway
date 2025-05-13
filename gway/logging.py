import os
import sys
import logging
import logging.handlers


def setup_logging(*, 
                 logfile=None, logdir="logs", prog_name="gway",
                 loglevel="INFO", pattern=None, backup_count=7):
    """Globally configure logging with optional rotating file and console handlers."""
    
    # Determine log level
    loglevel = getattr(logging, str(loglevel).upper(), logging.INFO)
    
    # Ensure logs directory exists if file logging is enabled
    if logfile:
        os.makedirs(logdir, exist_ok=True)
        if not os.path.isabs(logfile):
            logfile = os.path.join(os.getcwd(), logdir, logfile)
    
    # Define default pattern (now using funcName instead of filename). Only time, no date.
    # TODO: Replace funcName with the name of the python script followed by : then the line number
    pattern = pattern or '%(asctime)s %(levelname)s [%(name)s] %(filename)s:%(lineno)d - %(message)s'

    # Clear existing handlers to avoid duplicates
    logger = logging.getLogger()
    if logger.handlers:
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
    logger.setLevel(loglevel)

    # File handler (rotating daily at midnight)
    if logfile:
        file_handler = logging.handlers.TimedRotatingFileHandler(
            logfile, when='midnight', interval=1, backupCount=backup_count, encoding='utf-8'
        )
        file_handler.setLevel(loglevel)
        file_handler.setFormatter(logging.Formatter(pattern, datefmt='%H:%M:%S'))
        logger.addHandler(file_handler)

    # Initial log message
    sep = "-" * 70
    cmd_args = " ".join(sys.argv[1:])
    logger.info(f"\n{sep}\n> {prog_name or '%prog'} {cmd_args}\n{sep}")
    logger.info(f"Loglevel set to {loglevel} ({logging.getLevelName(loglevel)})")

    return logger
