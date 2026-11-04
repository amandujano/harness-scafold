import unittest

from app import greeting


class TestGreeting(unittest.TestCase):
    def test_greeting_returns_project_name(self):
        self.assertEqual(greeting(), "{{name}}")
