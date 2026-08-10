#!/usr/bin/env python3
"""Build the combined GXR 1.51 English-slot -> Simplified Chinese candidate.

Experiment 2 mapped persistent English ID 1 to runtime ID 6 only while camera
settings were copied. Real-hardware testing showed that this was insufficient:
the language menu writes its selected ID directly to the runtime object before
calling the common language initializer.

This candidate keeps the experiment-2 configuration mappings and additionally
maps ID 1 to ID 6 at that common initializer. Resource containers are not
modified.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import build_gxr151_english_runtime_id6_candidate as config_candidate
import build_gxr151_english_runtime_id6_wrapper_exploratory as wrapper_candidate


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "GXR Update" / "Firmware rel 1.51" / "ilaunch3"
OUTPUT_DIR = ROOT / "analysis" / "gxr151_english_id6_combined_candidate"
OUTPUT = OUTPUT_DIR / "ilaunch3"
REPORT = OUTPUT_DIR / "report.json"


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    config_candidate.main()

    original = SOURCE.read_bytes()
    stage2 = config_candidate.OUTPUT.read_bytes()
    stage2_report = json.loads(
        config_candidate.REPORT.read_text(encoding="utf-8")
    )

    wrapper_offset = wrapper_candidate.PATCH_FILE_OFFSET
    wrapper_original = wrapper_candidate.ORIGINAL_BLOCK
    wrapper_replacement = wrapper_candidate.candidate_block()
    if len(wrapper_replacement) != len(wrapper_original):
        raise AssertionError("language initializer replacement length changed")
    if (
        original[wrapper_offset : wrapper_offset + len(wrapper_original)]
        != wrapper_original
    ):
        raise ValueError("official language initializer patch site does not match")
    if (
        stage2[wrapper_offset : wrapper_offset + len(wrapper_original)]
        != wrapper_original
    ):
        raise ValueError("experiment-2 patches overlap language initializer")

    patched = bytearray(stage2)
    patched[
        wrapper_offset : wrapper_offset + len(wrapper_replacement)
    ] = wrapper_replacement
    new_checksum = config_candidate.firmware_checksum(patched)
    config_candidate.set_be32(
        patched,
        config_candidate.CHECKSUM_OFFSET,
        new_checksum,
    )
    if (
        config_candidate.be32(patched, config_candidate.CHECKSUM_OFFSET)
        != config_candidate.firmware_checksum(patched)
    ):
        raise AssertionError("combined candidate checksum verification failed")

    differences = config_candidate.changed_offsets(original, patched)
    allowed = {
        int(offset)
        for offset in stage2_report["changed_offsets"]
    }
    allowed.update(
        range(wrapper_offset, wrapper_offset + len(wrapper_replacement))
    )
    allowed.update(
        range(
            config_candidate.CHECKSUM_OFFSET,
            config_candidate.CHECKSUM_OFFSET + 4,
        )
    )
    if any(offset not in allowed for offset in differences):
        raise AssertionError("combined candidate changed unapproved bytes")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(patched)
    report = {
        "status": "EXPERIMENT_3_STATIC_CANDIDATE",
        "purpose": (
            "Keep Japanese ID 0 unchanged and map the Japan-region English "
            "slot ID 1 to Simplified Chinese ID 6 both during configuration "
            "copy and at the common language initializer"
        ),
        "source": str(SOURCE),
        "output": str(OUTPUT),
        "file_size": len(original),
        "sha256_before": sha256(original),
        "sha256_after": sha256(patched),
        "checksum_before": stage2_report["checksum_before"],
        "checksum_after": f"0x{new_checksum:08X}",
        "patches": stage2_report["patches"]
        + [
            {
                "name": "common_language_initializer_english_to_chinese",
                "va": f"0x{wrapper_candidate.PATCH_VA:08X}",
                "file_offset": f"0x{wrapper_offset:X}",
                "length": len(wrapper_replacement),
                "called_subsystems": [
                    "0x201D1EFC",
                    "0x201D4F24",
                    "0x201D83EC",
                ],
            }
        ],
        "changed_byte_count": len(differences),
        "changed_offsets": differences,
        "resource_files_modified": [],
        "mapping": {
            "language_0": "Japanese unchanged",
            "language_1": "Simplified Chinese resources, fonts, and UI init",
            "language_2_to_10": "unchanged",
        },
        "hardware_evidence": (
            "Experiment 2 was stable but selecting English still loaded English. "
            "Disassembly then confirmed four UI paths write the menu ID directly "
            "and call the common initializer, bypassing experiment 2's mapping."
        ),
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
