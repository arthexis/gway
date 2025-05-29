import re
import time as _time
import datetime
import requests


def now(*, utc=False) -> "datetime":
    """Return the current datetime object."""
    return datetime.datetime.now(datetime.timezone.utc) if utc else datetime.datetime.now()


def now_plus(*, seconds=0, utc=False) -> "datetime":
    """Return current datetime plus given seconds."""
    base = now(utc=utc)
    return base + datetime.timedelta(seconds=seconds)


def time(*, utc=False) -> str:
    """Return the current time of day as HH:MM:SS."""
    struct_time = _time.gmtime() if utc else _time.localtime()
    return _time.strftime('%H:%M:%S', struct_time)


def timestamp(*, utc=False) -> str:
    """Return the current timestamp in ISO-8601 format."""
    return now(utc=utc).isoformat().replace("+00:00", "Z" if utc else "")


def to_download(filesize):
    """ 
    Prompt: Create a python function that takes a file size such as 100 MB or 1.76 GB 
    (pick a wide array of units) and then calculates the possible time to download 
    it within 4 ranges. You choose the ranges logarithmically. Then, perform a quick 
    check against google to let the user know what their current range is.
    """
    
    # 1. Size parsing
    def parse_size(size_str):
        """
        Parse a size string like '1.76 GB', '500kb', '1024 B', '3.2 GiB'
        into a number of bytes (float).
        Accepts decimal (k=1e3) or binary (Ki=2**10) prefixes.
        """
        size_str = size_str.strip()
        pattern = r"^([\d\.]+)\s*([kKmMgGtTpP])([iI])?[bB]?$"
        m = re.match(pattern, size_str)
        if not m:
            raise ValueError(f"Unrecognized size format: {size_str!r}")
        num, prefix, binary = m.group(1,2,3)
        num = float(num)
        exp = {"k":1, "m":2, "g":3, "t":4, "p":5}[prefix.lower()]
        if binary:
            factor = 2 ** (10 * exp)
        else:
            factor = 10 ** (3 * exp)
        return num * factor

    # 2. Human‐friendly duration
    def format_duration(seconds):
        if seconds < 1:
            return f"{seconds*1000:.1f} ms"
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        parts = []
        if h: parts.append(f"{int(h)} h")
        if m: parts.append(f"{int(m)} m")
        if s or not parts: parts.append(f"{s:.1f} s")
        return " ".join(parts)

    # 3. Estimate times at four speeds
    SPEED_BRACKETS = [
        (1e3,   "1 kB/s (≈8 kbps)"),
        (1e5,   "100 kB/s (≈0.8 Mbps)"),
        (1e7,   "10 MB/s (≈80 Mbps)"),
        (1e9,   "1 GB/s (≈8 Gbps)"),
    ]

    def estimate_download_times(size_str):
        size_bytes = parse_size(size_str)
        estimates = []
        for speed, label in SPEED_BRACKETS:
            t = size_bytes / speed
            estimates.append((label, format_duration(t)))
        return estimates

    # 4. Quick live check against Google
    def measure_current_speed(test_url=None):
        """
        Downloads a small Google logo and measures
        average download speed in bytes/sec.
        """
        if test_url is None:
            test_url = "https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_272x92dp.png"
        start = time.time()
        r = requests.get(test_url, stream=True, timeout=10)
        total = 0
        for chunk in r.iter_content(1024):
            total += len(chunk)
        elapsed = time.time() - start
        return total / elapsed  # bytes per second

    def classify_speed(bps):
        """
        Find which bracket your speed bps falls into.
        """
        for i, (speed, label) in enumerate(SPEED_BRACKETS):
            # if it's slower than midpoint to next bracket, it's here
            if i == len(SPEED_BRACKETS)-1 or bps < (speed * (SPEED_BRACKETS[i+1][0] / speed)**0.5):
                return label
        return SPEED_BRACKETS[-1][1]

    # 5. Putting it all together
    def download_time_report(size_str):
        print(f"Estimating download times for {size_str!r}:\n")
        for label, t in estimate_download_times(size_str):
            print(f" • At {label}: {t}")
        try:
            print("\nMeasuring your current download speed…")
            speed = measure_current_speed()
            human = format_duration(parse_size('1 B') / speed)  # seconds to download 1 B
            print(f" → Detected ≈{speed/1024:.1f}\u00A0kB/s ({format_duration(size=1/speed)})")
            bracket = classify_speed(speed)
            print(f"   You’re in the **{bracket}** range.")
        except Exception as e:
            print(f" (Could not measure live speed: {e})")

    download_time_report(filesize)
