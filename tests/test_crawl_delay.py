"""Crawl-delay handling: only reviewed hosts proceed, and they are paced."""
import os, sys, unittest, urllib.robotparser
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import rv_master_disk as worker


def parser_for(lines):
    p = urllib.robotparser.RobotFileParser()
    p.parse(lines)
    return p


class CrawlDelay(unittest.TestCase):
    def setUp(self):
        self.saved = worker.robots_policy
        worker.LAST_FETCH.clear()

    def tearDown(self):
        worker.robots_policy = self.saved
        worker.LAST_FETCH.clear()

    def test_unreviewed_host_with_delay_is_held(self):
        worker.robots_policy = lambda host: (parser_for(["User-agent: *", "Allow: /"]), 10.0)
        with self.assertRaises(worker.Held):
            worker.robots_check("https://www.lippert.com/a.pdf", sleep=lambda s: None)

    def test_reviewed_host_waits_out_the_delay(self):
        worker.robots_policy = lambda host: (parser_for(["User-agent: *", "Allow: /"]), 10.0)
        now = [1000.0]; slept = []
        clock = lambda: now[0]
        def sleep(s):
            slept.append(s); now[0] += s
        worker.robots_check("https://www.roadmasterinc.com/support/manuals", sleep=sleep, clock=clock)
        self.assertEqual(slept, [])
        now[0] += 3
        worker.robots_check("https://www.roadmasterinc.com/a.pdf", sleep=sleep, clock=clock)
        self.assertEqual(len(slept), 1)
        self.assertAlmostEqual(slept[0], 7.0)

    def test_reviewed_host_over_cap_is_held(self):
        worker.robots_policy = lambda host: (parser_for(["User-agent: *", "Allow: /"]), 600.0)
        with self.assertRaises(worker.Held):
            worker.robots_check("https://www.roadmasterinc.com/a.pdf", sleep=lambda s: None)

    def test_robots_disallow_still_wins(self):
        worker.robots_policy = lambda host: (parser_for(["User-agent: *", "Disallow: /"]), 10.0)
        with self.assertRaises(worker.Held):
            worker.robots_check("https://www.roadmasterinc.com/a.pdf", sleep=lambda s: None)


if __name__ == "__main__":
    unittest.main()
