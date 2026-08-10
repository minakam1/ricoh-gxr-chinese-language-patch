from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from pathlib import Path

import gxr_firmware_modifier as modifier


class ModifierTests(unittest.TestCase):
    def test_encode_bl_known_targets(self) -> None:
        self.assertEqual(modifier.encode_bl(0x20077FE0, 0x2007785C), bytes.fromhex("fe ff fe 1f"))
        self.assertEqual(modifier.encode_bl(0x201C0F60, 0x201D1EFC), bytes.fromhex("fe 00 43 e7"))

    def test_replacement_lengths_match(self) -> None:
        self.assertEqual(len(modifier.english_language_init()), len(modifier.LANGUAGE_INIT_ORIGINAL))
        self.assertEqual(len(modifier.unlock_wrapper()), len(modifier.UNLOCK_WRAPPER_ORIGINAL))

    @unittest.skipUnless(os.environ.get("GXR151_OFFICIAL_DIR"), "需要用户自己的官方固件")
    def test_both_modes_against_user_fixture(self) -> None:
        source = Path(os.environ["GXR151_OFFICIAL_DIR"])
        files = modifier.read_firmware(source)
        english, _ = modifier.patch_english(files["ilaunch3"])
        unlock, _ = modifier.patch_unlock(files["ilaunch3"])
        self.assertEqual(modifier.sha256(english), modifier.ENGLISH_EXPECTED_SHA256)
        self.assertEqual(modifier.sha256(unlock), modifier.UNLOCK_EXPECTED_SHA256)

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "Ricoh_GXR_1.51_水水固件_英文替换版.zip"
            patched, patches = modifier.patch_english(files["ilaunch3"])
            manifest = modifier.build_manifest("english", files, patched, patches)
            modifier.write_output(output, "english", files, patched, manifest)
            with zipfile.ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                self.assertTrue(
                    all(
                        name.startswith("Ricoh_GXR_1.51_水水固件_英文替换版/")
                        for name in archive.namelist()
                    )
                )
                self.assertEqual(
                    len([name for name in archive.namelist() if "/SD_ROOT/" in name]),
                    29,
                )
            output_directory = Path(temp) / "Ricoh_GXR_1.51_水水固件_英文替换版"
            modifier.write_output(
                output_directory,
                "english",
                files,
                patched,
                manifest,
            )
            self.assertEqual(len(list((output_directory / "SD_ROOT").iterdir())), 29)
            self.assertEqual(
                modifier.sha256((output_directory / "SD_ROOT" / "ilaunch3").read_bytes()),
                modifier.ENGLISH_EXPECTED_SHA256,
            )


if __name__ == "__main__":
    unittest.main()
