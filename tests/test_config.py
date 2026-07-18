import os
import sqlite3
import unittest
from unittest.mock import patch

from forge.agent.executor import ask
from forge.config import OPENAI_KEY_ERROR, OpenAIConfigurationError, require_openai_api_key


class ConfigurationTests(unittest.TestCase):
    def test_missing_openai_key_has_setup_message(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            with self.assertRaisesRegex(OpenAIConfigurationError, "OpenAI API key not found"):
                require_openai_api_key()

    def test_ask_requires_openai_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            with self.assertRaisesRegex(OpenAIConfigurationError, "Create a .env file"):
                ask(sqlite3.connect(":memory:"), "What are the top complaint categories?")

    def test_error_message_is_complete(self):
        self.assertIn("OPENAI_API_KEY=your_key_here", OPENAI_KEY_ERROR)


if __name__ == "__main__":
    unittest.main()
