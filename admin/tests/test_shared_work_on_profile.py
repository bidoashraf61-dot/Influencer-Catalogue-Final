"""Nobody sees a colleague's work; a shared selection and its campaign land on the invited person's profile (owner, 2026-10-18)."""
import unittest

import portal


class SampleIds(unittest.TestCase):
    def test_sample_ids_helper_exists(self):
        self.assertTrue(callable(portal.sample_ids_for))


if __name__ == "__main__":
    unittest.main()
