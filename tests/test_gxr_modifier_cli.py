from __future__ import annotations

import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import gxr_modifier_cli as cli


class CliTests(unittest.TestCase):
    def test_choose_mode_retries(self) -> None:
        answers = iter(("x", "3", "2"))
        self.assertEqual(cli.choose_mode(lambda _prompt: next(answers)), "unlock")

    def test_unique_output_adds_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "official.zip"
            source.touch()
            first = Path(temp) / "Ricoh_GXR_1.51_水水固件_英文替换版.zip"
            first.touch()
            self.assertEqual(
                cli.unique_output(source, "english").name,
                "Ricoh_GXR_1.51_水水固件_英文替换版_2.zip",
            )

    def test_main_waits_for_next_source_after_invalid_file(self) -> None:
        answers = iter(("/tmp/next.zip",))

        def next_answer(_prompt: str) -> str:
            try:
                return next(answers)
            except StopIteration as error:
                raise EOFError from error

        with mock.patch.object(
            cli,
            "run",
            side_effect=(ValueError("不是官方固件"), Path("/tmp/output.zip")),
        ) as run_mock:
            self.assertEqual(cli.main(["/tmp/wrong.zip"], next_answer), 0)
        self.assertEqual(run_mock.call_count, 2)

    @unittest.skipUnless(os.environ.get("GXR151_OFFICIAL_DIR"), "需要用户自己的官方固件")
    def test_directory_drag_flow(self) -> None:
        source = Path(os.environ["GXR151_OFFICIAL_DIR"])
        with tempfile.TemporaryDirectory() as temp:
            fixture = Path(temp) / "official"
            fixture.mkdir()
            for path in source.iterdir():
                if path.is_file():
                    shutil.copy2(path, fixture / path.name)
            output = cli.run(fixture, lambda _prompt: "1")
            self.assertTrue(output.is_file())
            self.assertEqual(output.name, "Ricoh_GXR_1.51_水水固件_英文替换版.zip")
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(
                    len([name for name in archive.namelist() if "/SD_ROOT/" in name]),
                    29,
                )


if __name__ == "__main__":
    unittest.main()
