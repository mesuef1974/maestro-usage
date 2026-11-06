"""جدول مستودعات المشروع: يُزرع على قاعدة جديدة، ولا يتضاعف، ويعود إن حُذفت صفوفه."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import usage_db  # noqa: E402


class ProjectRepos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "t.sqlite3")
        self.con = usage_db.connect(self.path)
        self.addCleanup(self.con.close)

    def repos(self):
        return {r[0]: r[1:] for r in self.con.execute("SELECT repo, visibility, role, local_dir FROM project_repos")}

    def test_seeded_on_fresh_db(self):
        self.assertEqual(self.repos(), {r[0]: r[1:] for r in usage_db.REPO_SEEDS})

    def test_reconnect_does_not_duplicate(self):
        usage_db.init_schema(self.con)
        self.assertEqual(len(self.repos()), len(usage_db.REPO_SEEDS))

    def test_rows_return_after_delete(self):
        self.con.execute("DELETE FROM project_repos")
        self.con.commit()
        usage_db.init_schema(self.con)
        self.assertEqual(len(self.repos()), len(usage_db.REPO_SEEDS))


if __name__ == "__main__":
    unittest.main()
