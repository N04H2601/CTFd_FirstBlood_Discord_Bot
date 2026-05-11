import tempfile
import unittest
from pathlib import Path

from main import (
    Announcement,
    Challenge,
    FirstBloodStore,
    first_solve_snapshot,
    normalize_ctfd_api_url,
    normalize_solve,
)


class FirstBloodStateTests(unittest.TestCase):
    def make_store(self, temp_dir: str) -> FirstBloodStore:
        return FirstBloodStore(Path(temp_dir) / "state.sqlite3")

    def make_solve(
        self,
        challenge_id: int,
        name: str,
        date: str,
        account_id: int = 1,
    ):
        return normalize_solve(
            challenge_id,
            {"name": name, "date": date, "account_id": account_id},
        )

    def test_normalize_ctfd_api_url_accepts_common_forms(self):
        self.assertEqual(
            normalize_ctfd_api_url("https://ctf.example.com"),
            "https://ctf.example.com/api/v1",
        )
        self.assertEqual(
            normalize_ctfd_api_url("https://ctf.example.com/api/v1"),
            "https://ctf.example.com/api/v1",
        )
        self.assertEqual(
            normalize_ctfd_api_url("https://ctf.example.com/api/v1/challenges"),
            "https://ctf.example.com/api/v1",
        )

    def test_first_solve_snapshot_uses_earliest_valid_date(self):
        first = first_solve_snapshot(
            10,
            [
                {
                    "name": "late",
                    "date": "2026-05-01T12:00:00.000000Z",
                    "account_id": 2,
                },
                {
                    "name": "early",
                    "date": "2026-05-01T11:00:00+00:00",
                    "account_id": 1,
                },
            ],
        )

        self.assertIsNotNone(first)
        self.assertEqual(first.solver_name, "early")

    def test_store_is_idempotent_after_announcement(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            challenge = Challenge(id=1, name="crypto")
            solve = self.make_solve(1, "team-a", "2026-05-01T10:00:00Z")
            announcement = Announcement(1, "crypto", solve)

            self.assertTrue(store.observe_first_solve(challenge, solve))
            store.mark_announced(announcement, message_id=123)
            self.assertFalse(store.observe_first_solve(challenge, solve))
            self.assertEqual(store.get(1)["status"], "announced")
            store.close()

    def test_failed_announcement_is_retried_for_same_solve(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            challenge = Challenge(id=2, name="web")
            solve = self.make_solve(2, "team-b", "2026-05-01T10:00:00Z")
            announcement = Announcement(2, "web", solve)

            self.assertTrue(store.observe_first_solve(challenge, solve))
            store.mark_failed(announcement, "discord unavailable")
            self.assertTrue(store.observe_first_solve(challenge, solve))
            self.assertTrue(store.is_sendable(announcement))
            store.close()

    def test_removed_solves_make_old_pending_announcement_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            challenge = Challenge(id=3, name="pwn")
            old_solve = self.make_solve(3, "team-old", "2026-05-01T10:00:00Z")
            old_announcement = Announcement(3, "pwn", old_solve)
            new_solve = self.make_solve(
                3,
                "team-new",
                "2026-05-01T10:05:00Z",
                account_id=4,
            )

            self.assertTrue(store.observe_first_solve(challenge, old_solve))
            store.mark_no_solves(challenge)
            self.assertFalse(store.is_sendable(old_announcement))
            self.assertTrue(store.observe_first_solve(challenge, new_solve))
            row = store.get(3)
            self.assertEqual(row["status"], "pending")
            self.assertEqual(row["solver_name"], "team-new")
            store.close()

    def test_legacy_csv_syncs_existing_solve_without_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            csv_path = directory_path / "announced_first_bloods.csv"
            csv_path.write_text("4\n", encoding="utf-8")
            store = FirstBloodStore(directory_path / "state.sqlite3")
            self.assertEqual(store.migrate_legacy_csv(csv_path), 1)

            challenge = Challenge(id=4, name="forensics")
            solve = self.make_solve(4, "team-c", "2026-05-01T10:00:00Z")
            self.assertFalse(store.observe_first_solve(challenge, solve))
            row = store.get(4)
            self.assertEqual(row["status"], "announced")
            self.assertEqual(row["legacy_csv"], 0)
            store.close()

    def test_legacy_csv_announces_new_solve_after_empty_state_seen(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            csv_path = directory_path / "announced_first_bloods.csv"
            csv_path.write_text("5\n", encoding="utf-8")
            store = FirstBloodStore(directory_path / "state.sqlite3")
            store.migrate_legacy_csv(csv_path)

            challenge = Challenge(id=5, name="misc")
            store.mark_no_solves(challenge)
            solve = self.make_solve(5, "team-d", "2026-05-01T10:10:00Z")
            self.assertTrue(store.observe_first_solve(challenge, solve))
            self.assertEqual(store.get(5)["status"], "pending")
            store.close()


if __name__ == "__main__":
    unittest.main()
