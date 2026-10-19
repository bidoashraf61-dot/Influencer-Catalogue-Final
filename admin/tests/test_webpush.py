"""Stdlib Web Push crypto (item 168): RFC 8291 worked example, GCM spec vectors, ES256.

    python3 admin/tests/test_webpush.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import webpush as wp  # noqa: E402


class Crypto(unittest.TestCase):
    def test_gcm_spec_vectors(self):
        # McGrew & Viega, GCM spec test cases 2 and 3.
        out = wp.aes_gcm_encrypt(bytes(16), bytes(12), bytes(16))
        self.assertEqual(out.hex(), "0388dace60b6a392f328c2b971b2fe78" "ab6e47d42cec13bdf53a67b21257bddf")
        key = bytes.fromhex("feffe9928665731c6d6a8f9467308308")
        iv = bytes.fromhex("cafebabefacedbaddecaf888")
        pt = bytes.fromhex("d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a72"
                           "1c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b391aafd255")
        out = wp.aes_gcm_encrypt(key, iv, pt)
        self.assertEqual(out[:-16].hex(), "42831ec2217774244b7221b784d0d49ce3aa212f2c02a4e035c17e2329aca12e"
                                          "21d514b25466931c7d8f6a5aac84aa051ba30b396a0aac973d58e091473f5985")
        self.assertEqual(out[-16:].hex(), "4d5c2af327cd64a62cf35abd2ba6fab4")

    def test_rfc8291_example(self):
        as_priv = int.from_bytes(wp.unb64u("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big")
        self.assertEqual(wp.b64u(wp.encode_point(wp.mul(as_priv))),
                         "BP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A8")
        body = wp.encrypt(b"When I grow up, I want to be a watermelon",
                          wp.unb64u("BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"),
                          wp.unb64u("BTBZMqHH6r4Tts7J_aSIgg"), as_private=as_priv,
                          salt=wp.unb64u("DGv6ra1nlYgDCS1FRnbzlw"))
        self.assertEqual(wp.b64u(body),
                         "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6Tl"
                         "zAC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")

    def test_es256_round_trip(self):
        d = wp.new_private()
        pub = wp.mul(d)
        sig = wp.sign(d, b"hello")
        self.assertTrue(wp.verify(pub, b"hello", sig))
        self.assertFalse(wp.verify(pub, b"hellp", sig))

    def test_against_openssl_when_available(self):
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError:
            self.skipTest("cryptography not installed (fine on the server)")
        d = wp.new_private()
        pub = wp.mul(d)
        key = ec.EllipticCurvePublicNumbers(pub[0], pub[1], ec.SECP256R1()).public_key()
        sig = wp.sign(d, b"vapid")
        key.verify(encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")),
                   b"vapid", ec.ECDSA(hashes.SHA256()))
        other = ec.generate_private_key(ec.SECP256R1())
        on = other.public_key().public_numbers()
        mine = ec.derive_private_key(d, ec.SECP256R1())
        self.assertEqual(wp.ecdh(d, (on.x, on.y)), other.exchange(ec.ECDH(), mine.public_key()))
        for n in (0, 1, 15, 16, 17, 100, 4000):
            k, iv, pt = bytes(range(16)), bytes(range(12)), bytes(i % 251 for i in range(n))
            self.assertEqual(wp.aes_gcm_encrypt(k, iv, pt), AESGCM(k).encrypt(iv, pt, None))

    def test_vapid_header_shape(self):
        h = wp.vapid_header("https://fcm.googleapis.com/fcm/send/abc")
        self.assertTrue(h.startswith("vapid t=") and ", k=B" in h)
        token = h[len("vapid t="):h.index(",")]
        head, body, sig = token.split(".")
        import json
        self.assertEqual(json.loads(wp.unb64u(body))["aud"], "https://fcm.googleapis.com")
        self.assertTrue(wp.verify(wp.keys()[1], (head + "." + body).encode(), wp.unb64u(sig)))


if __name__ == "__main__":
    import os
    import tempfile
    wp.KEY_FILE = os.path.join(tempfile.mkdtemp(), ".vapid-key")
    unittest.main()
