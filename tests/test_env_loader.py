import os
import tempfile
import unittest
from pathlib import Path

from shipguard.env_loader import load_env_file


class LoadEnvFileTests(unittest.TestCase):
    def test_loads_values_from_dotenv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "SHIPGUARD_LLM_BASE_URL=https://example.test/v1",
                        "export SHIPGUARD_LLM_MODEL=test-model",
                        "SHIPGUARD_GITHUB_TOKEN='test-token'",
                    ]
                ),
                encoding="utf-8",
            )

            with self._clean_env(
                "SHIPGUARD_LLM_BASE_URL",
                "SHIPGUARD_LLM_MODEL",
                "SHIPGUARD_GITHUB_TOKEN",
            ):
                load_env_file(env_path)

                self.assertEqual(
                    os.environ["SHIPGUARD_LLM_BASE_URL"],
                    "https://example.test/v1",
                )
                self.assertEqual(os.environ["SHIPGUARD_LLM_MODEL"], "test-model")
                self.assertEqual(os.environ["SHIPGUARD_GITHUB_TOKEN"], "test-token")

    def test_does_not_override_existing_environment_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "SHIPGUARD_GITHUB_TOKEN=file-token\n",
                encoding="utf-8",
            )

            with self._clean_env("SHIPGUARD_GITHUB_TOKEN"):
                os.environ["SHIPGUARD_GITHUB_TOKEN"] = "exported-token"

                load_env_file(env_path)

                self.assertEqual(os.environ["SHIPGUARD_GITHUB_TOKEN"], "exported-token")

    def test_can_override_existing_environment_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "SHIPGUARD_GITHUB_TOKEN=file-token\n",
                encoding="utf-8",
            )

            with self._clean_env("SHIPGUARD_GITHUB_TOKEN"):
                os.environ["SHIPGUARD_GITHUB_TOKEN"] = "exported-token"

                load_env_file(env_path, override=True)

                self.assertEqual(os.environ["SHIPGUARD_GITHUB_TOKEN"], "file-token")

    def _clean_env(self, *names: str):
        class CleanEnv:
            def __enter__(self) -> None:
                self.previous = {name: os.environ.get(name) for name in names}
                for name in names:
                    os.environ.pop(name, None)

            def __exit__(self, *args: object) -> None:
                for name in names:
                    os.environ.pop(name, None)
                for name, value in self.previous.items():
                    if value is not None:
                        os.environ[name] = value

        return CleanEnv()


if __name__ == "__main__":
    unittest.main()
