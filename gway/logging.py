import os
import sys
import logging
import logging.handlers
import traceback


class FilteredTracebackFormatter(logging.Formatter):
    """
    A Formatter that, when an exception is logged, strips out any
    traceback frames whose filename path contains 'gway/gway', counts them,
    and replaces them with a summary line—unless gw.debug_mode is True.
    """

    def formatException(self, ei):
        exc_type, exc_value, tb = ei
        all_frames = traceback.extract_tb(tb)
        kept_frames = []
        skipped = 0

        # Check if debug mode is enabled
        debug_mode = False
        try:
            from gway import gw
            debug_mode = getattr(gw, "debug_mode", False)
        except Exception:
            pass

        for frame in all_frames:
            norm = frame.filename.replace('\\', '/')
            if '/gway/gway/' in norm and not debug_mode:
                skipped += 1
            else:
                kept_frames.append(frame)

        formatted = []
        if kept_frames:
            formatted.extend(traceback.format_list(kept_frames))
        if skipped and not debug_mode:
            formatted.append(f'  <... {skipped} frame(s) in gway internals skipped ...>\n')
        formatted.extend(traceback.format_exception_only(exc_type, exc_value))
        return ''.join(formatted)


def setup_logging(*,
                  logfile=None, logdir="logs", prog_name="gway",
                  loglevel="INFO", pattern=None, backup_count=7):
    """Globally configure logging with filtered tracebacks."""

    loglevel = getattr(logging, str(loglevel).upper(), logging.INFO)

    if logfile:
        os.makedirs(logdir, exist_ok=True)
        if not os.path.isabs(logfile):
            logfile = os.path.join(os.getcwd(), logdir, logfile)

    pattern = pattern or '%(asctime)s %(levelname)s [%(name)s] %(filename)s:%(lineno)d - %(message)s'

    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
    root.setLevel(loglevel)

    formatter = FilteredTracebackFormatter(pattern, datefmt='%H:%M:%S')

    if logfile:
        file_h = logging.handlers.TimedRotatingFileHandler(
            logfile, when='midnight', interval=1,
            backupCount=backup_count, encoding='utf-8'
        )
        file_h.setLevel(loglevel)
        file_h.setFormatter(formatter)
        root.addHandler(file_h)

    sep = "-" * 70
    cmd_args = " ".join(sys.argv[1:])
    root.info(f"\n{sep}\n> {prog_name} {cmd_args}\n{sep}")
    root.info(f"Loglevel set to {loglevel} ({logging.getLevelName(loglevel)})")

    return root
