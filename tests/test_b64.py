import base64
import tempfile
from pathlib import Path
import unittest

from gway import gw


class B64Tests(unittest.TestCase):
    def test_encode_string(self):
        result = gw.b64.encode("hello")
        self.assertEqual(result, base64.b64encode(b"hello").decode())

    def test_decode_string(self):
        b64val = base64.b64encode(b"hello world").decode()
        result = gw.b64.decode(b64val)
        self.assertEqual(result, "hello world")

    def test_decode_to_file(self):
        data = b"\x00\x01\x02"
        b64val = base64.b64encode(data).decode()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "data.bin"
            path_str = gw.b64.decode(b64val, out=str(out))
            self.assertEqual(path_str, str(out))
            self.assertEqual(out.read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
