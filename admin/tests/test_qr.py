"""Stdlib QR encoder (item 169) against the qrcode package, every mask, versions 1-10.

    python3 admin/tests/test_qr.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import qr  # noqa: E402


class QR(unittest.TestCase):
    def test_matches_reference(self):
        try:
            import qrcode
            import qrcode.util
        except ImportError:
            self.skipTest("qrcode package not installed")
        texts = ["A", "https://influencer-catalogue.hellovoice.co.uk/admin/api/push/qr?h=" + "x" * 32,
                 "h" * 60, "y" * 120, "z" * 150, "w" * 200]
        for t in texts:
            for mask in range(8):
                ref = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0, mask_pattern=mask)
                ref.add_data(qrcode.util.QRData(t.encode(), mode=qrcode.util.MODE_8BIT_BYTE))
                ref.make(fit=True)
                want = [[1 if v else 0 for v in row] for row in ref.get_matrix()]
                self.assertEqual(qr.matrix(t, mask=mask), want, (len(t), mask, ref.version))

    def test_svg_and_limits(self):
        s = qr.svg("https://example.com/x")
        self.assertTrue(s.startswith("<svg") and "path" in s)
        with self.assertRaises(ValueError):
            qr.matrix("q" * 300)


if __name__ == "__main__":
    unittest.main()
