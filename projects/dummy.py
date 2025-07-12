# file: projects/dummy.py

def view_index():
    return "<h1>Dummy Index</h1>"


def setup_home():
    """Return the default home view for this project."""
    return "index"


def setup_links():
    """Return default navigation links for this project."""
    return ["about", "more"]
