"""A KAM's own new selection or campaign is handed to her (owner, 2026-10-18)."""
import unittest

import db
import kam_scope


class KamAutoAssign(unittest.TestCase):
    def test_new_items_belong_to_the_kam_who_made_them(self):
        sc = kam_scope.Scope([]); sc.email = "kam@x.test"
        kam_scope.begin(sc)
        try:
            sid = db.save_selection(None, "Mine", [], {}, None, None)
            cid = db.create_campaign("Mine too")
        finally:
            kam_scope.end()
        self.assertEqual(db.kam_of_item("selection", sid), "kam@x.test")
        self.assertEqual(db.kam_of_item("campaign", cid), "kam@x.test")
        other = db.save_selection(None, "Admin's", [], {}, None, None)
        self.assertIsNone(db.kam_of_item("selection", other))


if __name__ == "__main__":
    unittest.main()
