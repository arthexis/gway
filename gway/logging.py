import os
import sys
import logging
import logging.handlers


def setup_logging(*, 
                 logfile=None, logdir="logs", app_name=None,
                 loglevel="INFO", pattern=None, backup_count=7):
    """Globally configure logging with optional rotating file and console handlers."""
    
    # Determine log level
    loglevel = getattr(logging, str(loglevel).upper(), logging.INFO)
    
    # Ensure logs directory exists if file logging is enabled
    if logfile:
        os.makedirs(logdir, exist_ok=True)
        if not os.path.isabs(logfile):
            logfile = os.path.join(os.getcwd(), logdir, logfile)
    
    # Define default pattern (now using funcName instead of filename)
    pattern = pattern or '%(asctime)s %(levelname)s [%(name)s] %(funcName)s:%(lineno)d - %(message)s'

    # Clear existing handlers to avoid duplicates
    root_logger = logging.getLogger()
    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    # Set root logger level
    root_logger.setLevel(loglevel)

    # File handler (rotating daily at midnight)
    if logfile:
        file_handler = logging.handlers.TimedRotatingFileHandler(
            logfile, when='midnight', interval=1, backupCount=backup_count, encoding='utf-8'
        )
        file_handler.setLevel(loglevel)
        file_handler.setFormatter(logging.Formatter(pattern, datefmt='%Y-%m-%d %H:%M:%S'))
        root_logger.addHandler(file_handler)

    # Initial log message
    sep = "-" * 70
    cmd_args = " ".join(sys.argv[1:])
    root_logger.info(f"\n{sep}\n> {app_name or '%prog'} {cmd_args}\n{sep}")
