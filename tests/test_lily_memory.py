from pathlib import Path
import sqlite3
import tempfile
import unittest

from bots.lily.memory import ExperienceStore, route_key
from bots.lily.policies import adaptive


class MemoryTest(unittest.TestCase):
    def test_reopen_dedup_and_censor_change_route_choice(self):
        a = dict(node=10, sector=3, position=[1., 2., 0.], item_bin=0, **{"class": "patrol"}, utility=1, cost=1)
        b = dict(a, node=20, position=[4., 2., 0.], utility=1.1)
        ak, bk = (route_key("map-v1", x, [0, 0, 0]) for x in (a, b))
        self.assertEqual(ak, route_key("map-v1", dict(a, node=77), [0, 0, 0]))
        self.assertNotEqual(ak, route_key("map-v2", a, [0, 0, 0]))
        obs = {"lily": {"offers": {"choices": [a, b]}, "sense": {"medium": "air", "facing": [0, 1, 0], "peers": []}}}
        def pick(store):
            context = {"state": {}, "undertaking": None, "directive": None,
                     "routes": {str(x["node"]): store.estimate(k) for x, k in ((a, ak), (b, bk))}, "skills": {}}
            return adaptive.decide(obs, context)["node"]
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "experience.sqlite3"
            s = ExperienceStore(db)
            self.assertEqual(pick(s), 20)
            for i, (key, status, result) in enumerate([(ak, "arrived", True), (bk, "failed", False), (ak, "lost", None)]):
                attempt = dict(run_id="run", world_epoch=1, life_epoch=2, action_seq=i + 1, sample_id=1,
                             policy_hash="a" * 64, skill="navigate", kind="route", key=key)
                episode = s.begin(attempt)
                outcome = dict(status=status, physical_success=result, duration_seconds=.4, damage=0, item_gain={})
                self.assertTrue(s.finish(episode, outcome))
                self.assertFalse(s.finish(episode, outcome))
            s.close()
            s = ExperienceStore(db)
            try:
                self.assertEqual(pick(s), 10)
                self.assertEqual(s.estimate(ak)["trials"], 1)
            finally:
                s.close()

    def test_existing_attempt_database_gains_an_idempotent_bank_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.sqlite3"
            old = sqlite3.connect(path)
            old.execute("CREATE TABLE attempts(episode TEXT PRIMARY KEY, environment_key TEXT NOT NULL, "
                        "identity TEXT NOT NULL, outcome TEXT, success INTEGER, duration REAL)")
            old.execute("INSERT INTO attempts VALUES('historical','motor','{}','{}',1,.25)")
            old.commit()
            old.close()
            store = ExperienceStore(path)
            record = dict(task_id="first", run_id="r", position=[1., 2., 3.], policy_hash="a"*64)
            other = dict(record, task_id="second")
            independent = dict(record, task_id="other-run", run_id="s")
            try:
                self.assertEqual(store.estimate("motor")["wins"], 1)
                self.assertTrue(store.begin_bank(record))
                self.assertFalse(store.begin_bank(dict(record, position=[0., 0., 0.])))
                self.assertTrue(store.begin_bank(other))
                self.assertTrue(store.begin_bank(independent))
                outcome = dict(terminal="sampled_dry", physical_success=None)
                self.assertTrue(store.finish_bank("first", outcome))
                self.assertFalse(store.finish_bank("first", dict(terminal="supported_dry", physical_success=True)))
            finally:
                store.close()
            store = ExperienceStore(path)
            try:
                self.assertEqual(store.bank("first"), (record, outcome))
                recovered, = store.recover_banks("r")
                self.assertEqual((recovered[0], recovered[1]["terminal"]), (other, "restarted"))
                self.assertIsNone(recovered[1]["physical_success"])
                self.assertEqual(store.recover_banks("r"), [])
                self.assertEqual(store.bank("other-run"), (independent, None))
                self.assertEqual(store.estimate("motor")["wins"], 1)
            finally:
                store.close()

    def test_close_peer_can_select_learned_motor_over_available_route(self):
        offer = dict(node=4, sector=1, position=[4., 2., 0.], item_bin=0, **{"class": "patrol"}, utility=1, cost=1)
        obs = {"lily": {"offers": {"choices": [offer]}, "sense": {"position": [0, 0, 0], "facing": [0, 1, 0],
                       "medium": "air", "peers": [{"position": [.5, .1, 0]}]}}}
        unseen = {"attempts": 0, "trials": 0, "wins": 0, "probability": .5, "mean_seconds": None}
        context = {"undertaking": None, "state": {}, "directive": None, "routes": {"4": unseen},
                   "skills": {"sidestep": unseen, "forward-probe": unseen}}
        result = adaptive.decide(obs, context)
        self.assertEqual((result["action"], result["skill"]), ("motor", "sidestep"))
        context["skills"]["sidestep"] = dict(unseen, attempts=12, trials=4, probability=.17)
        self.assertEqual(adaptive.decide(obs, context)["skill"], "forward-probe")
        context["state"] = result["state"]
        self.assertEqual(adaptive.decide(obs, context)["node"], 4)
