import os
import sys
import logging
import logging.handlers
import traceback


class FilteredTracebackFormatter(logging.Formatter):
    """
    A Formatter that, when an exception is logged, strips out any
    traceback frames whose filename path contains 'gway/gway', counts them,
    and replaces them with a summary line.
    """

    def formatException(self, ei):
        exc_type, exc_value, tb = ei
        # Extract the raw list of FrameSummary objects
        all_frames = traceback.extract_tb(tb)
        kept_frames = []
        skipped = 0

        for frame in all_frames:
            # Normalize to forward slashes for cross-platform matching
            norm = frame.filename.replace('\\', '/')
            if '/gway/gway/' in norm:
                skipped += 1
            else:
                kept_frames.append(frame)

        # Reconstruct the formatted stack
        formatted = []
        if kept_frames:
            formatted.extend(traceback.format_list(kept_frames))
        if skipped:
            formatted.append(f'  <... {skipped} frame(s) in gway internals skipped ...>\n')
        # Finally add the exception type and message
        formatted.extend(traceback.format_exception_only(exc_type, exc_value))
        return ''.join(formatted)


def setup_logging(*,
                  logfile=None, logdir="logs", prog_name="gway",
                  loglevel="INFO", pattern=None, backup_count=7):
    """Globally configure logging with filtered tracebacks."""

    # Determine log level
    loglevel = getattr(logging, str(loglevel).upper(), logging.INFO)

    # Ensure logs directory exists if file logging is enabled
    if logfile:
        os.makedirs(logdir, exist_ok=True)
        if not os.path.isabs(logfile):
            logfile = os.path.join(os.getcwd(), logdir, logfile)

    # Default pattern: time, level, logger, file:line – message
    pattern = pattern or '%(asctime)s %(levelname)s [%(name)s] %(filename)s:%(lineno)d - %(message)s'

    # Clear existing handlers
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
    root.setLevel(loglevel)

    # Create our custom formatter
    formatter = FilteredTracebackFormatter(pattern, datefmt='%H:%M:%S')

    # File handler (rotating daily at midnight)
    if logfile:
        file_h = logging.handlers.TimedRotatingFileHandler(
            logfile, when='midnight', interval=1,
            backupCount=backup_count, encoding='utf-8'
        )
        file_h.setLevel(loglevel)
        file_h.setFormatter(formatter)
        root.addHandler(file_h)

    # Console handler
    console_h = logging.StreamHandler(sys.stderr)
    console_h.setLevel(loglevel)
    console_h.setFormatter(formatter)
    root.addHandler(console_h)

    # Initial log messages
    sep = "-" * 70
    cmd_args = " ".join(sys.argv[1:])
    root.info(f"\n{sep}\n> {prog_name} {cmd_args}\n{sep}")
    root.info(f"Loglevel set to {loglevel} ({logging.getLevelName(loglevel)})")

    return root
