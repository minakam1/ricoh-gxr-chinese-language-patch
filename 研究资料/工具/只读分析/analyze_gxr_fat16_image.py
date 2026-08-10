#!/usr/bin/env python3
"""Read-only FAT16 forensic inventory for the public GXR internal-storage image."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from datetime import datetime
from pathlib import Path


TARGETS = [
    b"LAUNCHA",
    b"IROM",
    b"IROM.DAT",
    b"IROM    DAT",
    b"IROM2.DAT",
    b"IROM2   DAT",
    b"PARAM",
    b"PARAM.DAT",
    b"PARAM   DAT",
    b"CONFIG",
    b"CONFIG.TST",
    b"CONFIG  TST",
    b"CONFIG.BAK",
    b"CONFIG  BAK",
    b"BADJ",
    b"BADJRAM.DAT",
    b"BADJRAM DAT",
    b"BADJROM.DAT",
    b"BADJROM DAT",
    b"BKIZ",
    b"BKIZRAM.DAT",
    b"BKIZRAM DAT",
    b"BKIZROM.DAT",
    b"BKIZROM DAT",
    b"BFPROM.DAT",
    b"BFPROM  DAT",
    b"BIFPROM.DAT",
    b"BIFPROM  DAT",
    b"COMMAND",
    b"COMMAND.NS1",
    b"COMMAND NS1",
    b"DBGMODE",
    b"DBGMODE.KEY",
    b"DBGMODE KEY",
    b"INCOPY",
    b"INCOPY.KEY",
    b"INCOPY  KEY",
    b"SCINST",
    b"SCINST.TST",
    b"SCINST  TST",
]


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def fat_datetime(date_word: int, time_word: int) -> str | None:
    if date_word == 0:
        return None
    year = 1980 + ((date_word >> 9) & 0x7F)
    month = (date_word >> 5) & 0x0F
    day = date_word & 0x1F
    hour = (time_word >> 11) & 0x1F
    minute = (time_word >> 5) & 0x3F
    second = (time_word & 0x1F) * 2
    try:
        return datetime(year, month, day, hour, minute, second).isoformat(" ")
    except ValueError:
        return None


def short_name(raw: bytes, deleted: bool) -> str:
    base = bytearray(raw[:8])
    ext = bytearray(raw[8:11])
    if deleted:
        base[0] = ord("?")
    base_text = bytes(base).decode("ascii", "replace").rstrip()
    ext_text = bytes(ext).decode("ascii", "replace").rstrip()
    return f"{base_text}.{ext_text}" if ext_text else base_text


def plausible_short_name(raw: bytes) -> bool:
    if len(raw) != 11 or raw[0] in (0x00,):
        return False
    allowed = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!#$%&'()-@^_`{}~ ")
    tail = raw[1:] if raw[0] == 0xE5 else raw
    return all(byte in allowed for byte in tail)


class Fat16Image:
    def __init__(self, image_path: Path):
        self.path = image_path
        self.data = image_path.read_bytes()
        if self.data[510:512] != b"\x55\xaa":
            raise ValueError("missing MBR signature")

        self.partition_lba = u32(self.data, 0x1BE + 8)
        self.partition_sectors = u32(self.data, 0x1BE + 12)
        self.partition_offset = self.partition_lba * 512
        boot = self.data[self.partition_offset : self.partition_offset + 512]
        if boot[510:512] != b"\x55\xaa":
            raise ValueError("missing FAT boot-sector signature")

        self.bytes_per_sector = u16(boot, 11)
        self.sectors_per_cluster = boot[13]
        self.reserved_sectors = u16(boot, 14)
        self.fat_count = boot[16]
        self.root_entry_count = u16(boot, 17)
        total16 = u16(boot, 19)
        self.total_sectors = total16 or u32(boot, 32)
        self.sectors_per_fat = u16(boot, 22)
        self.volume_label = boot[43:54].decode("ascii", "replace").rstrip()
        self.fs_label = boot[54:62].decode("ascii", "replace").rstrip()

        self.cluster_size = self.bytes_per_sector * self.sectors_per_cluster
        self.fat1_offset = self.partition_offset + self.reserved_sectors * self.bytes_per_sector
        self.fat_size = self.sectors_per_fat * self.bytes_per_sector
        self.fat2_offset = self.fat1_offset + self.fat_size
        self.root_offset = self.fat1_offset + self.fat_count * self.fat_size
        self.root_size = self.root_entry_count * 32
        root_sectors = (self.root_size + self.bytes_per_sector - 1) // self.bytes_per_sector
        self.data_offset = self.root_offset + root_sectors * self.bytes_per_sector
        self.data_sectors = (
            self.total_sectors
            - self.reserved_sectors
            - self.fat_count * self.sectors_per_fat
            - root_sectors
        )
        self.cluster_count = self.data_sectors // self.sectors_per_cluster
        self.fat = [
            u16(self.data, self.fat1_offset + index * 2)
            for index in range(self.cluster_count + 2)
        ]

    def cluster_offset(self, cluster: int) -> int:
        return self.data_offset + (cluster - 2) * self.cluster_size

    def cluster_bytes(self, cluster: int) -> bytes:
        offset = self.cluster_offset(cluster)
        return self.data[offset : offset + self.cluster_size]

    def chain(self, start_cluster: int) -> list[int]:
        if start_cluster < 2 or start_cluster >= len(self.fat):
            return []
        result: list[int] = []
        seen: set[int] = set()
        current = start_cluster
        while 2 <= current < 0xFFF8 and current < len(self.fat) and current not in seen:
            result.append(current)
            seen.add(current)
            current = self.fat[current]
            if current == 0:
                break
        return result

    def parse_entry(self, entry: bytes, location: int) -> dict | None:
        first = entry[0]
        if first == 0x00:
            return None
        attr = entry[11]
        if attr == 0x0F:
            return {
                "kind": "lfn",
                "deleted": first == 0xE5,
                "location": location,
            }
        if not plausible_short_name(entry[:11]):
            return None
        deleted = first == 0xE5
        cluster = u16(entry, 26)
        size = u32(entry, 28)
        return {
            "kind": "directory" if attr & 0x10 else "file",
            "name": short_name(entry[:11], deleted),
            "deleted": deleted,
            "attributes": f"0x{attr:02X}",
            "start_cluster": cluster,
            "size": size,
            "modified": fat_datetime(u16(entry, 24), u16(entry, 22)),
            "location": location,
        }

    def directory_region(self, cluster: int | None) -> tuple[bytes, int]:
        if cluster is None:
            return (
                self.data[self.root_offset : self.root_offset + self.root_size],
                self.root_offset,
            )
        chain = self.chain(cluster)
        if not chain:
            return self.cluster_bytes(cluster), self.cluster_offset(cluster)
        payload = b"".join(self.cluster_bytes(item) for item in chain)
        return payload, self.cluster_offset(chain[0])

    def walk_active_tree(self) -> list[dict]:
        output: list[dict] = []
        visited: set[int] = set()

        def walk(path: str, cluster: int | None) -> None:
            if cluster is not None:
                if cluster in visited:
                    return
                visited.add(cluster)
            region, base_offset = self.directory_region(cluster)
            for relative in range(0, len(region), 32):
                parsed = self.parse_entry(region[relative : relative + 32], base_offset + relative)
                if not parsed or parsed["kind"] == "lfn":
                    continue
                name = parsed["name"]
                parsed["path"] = f"{path}/{name}".replace("//", "/")
                output.append(parsed)
                if (
                    parsed["kind"] == "directory"
                    and not parsed["deleted"]
                    and name not in (".", "..")
                    and parsed["start_cluster"] >= 2
                ):
                    walk(parsed["path"], parsed["start_cluster"])

        walk("", None)
        return output

    def scan_directory_candidates(self) -> list[dict]:
        candidates: list[dict] = []
        regions = [(self.root_offset, self.root_size, "root")]
        for cluster in range(2, self.cluster_count + 2):
            regions.append((self.cluster_offset(cluster), self.cluster_size, f"cluster:{cluster}"))
        seen_locations: set[int] = set()
        for offset, size, source in regions:
            for location in range(offset, offset + size, 32):
                if location in seen_locations:
                    continue
                entry = self.data[location : location + 32]
                parsed = self.parse_entry(entry, location)
                if not parsed or parsed["kind"] == "lfn":
                    continue
                attr = int(parsed["attributes"], 16)
                if attr & 0xC0:
                    continue
                cluster = parsed["start_cluster"]
                if cluster >= self.cluster_count + 2 and cluster < 0xFFF8:
                    continue
                parsed["source"] = source
                candidates.append(parsed)
                seen_locations.add(location)
        return candidates

    def target_hits(self, active_tree: list[dict]) -> list[dict]:
        uppercase = self.data.upper()
        cluster_owners: dict[int, str] = {}
        for item in active_tree:
            if item["kind"] != "file" or item["deleted"]:
                continue
            for cluster in self.chain(item["start_cluster"]):
                cluster_owners[cluster] = item["path"]
        hits: list[dict] = []
        for target in TARGETS:
            start = 0
            while True:
                offset = uppercase.find(target, start)
                if offset < 0:
                    break
                if offset < self.data_offset:
                    area = "metadata"
                    cluster = None
                    allocated = None
                else:
                    cluster = 2 + (offset - self.data_offset) // self.cluster_size
                    area = f"cluster:{cluster}"
                    allocated = self.fat[cluster] != 0 if cluster < len(self.fat) else None
                hits.append(
                    {
                        "target": target.decode(),
                        "offset": offset,
                        "area": area,
                        "cluster": cluster,
                        "cluster_allocated": allocated,
                        "owner_path": cluster_owners.get(cluster) if cluster is not None else None,
                    }
                )
                start = offset + 1
        return hits

    def free_cluster_inventory(self) -> dict:
        free = [cluster for cluster in range(2, self.cluster_count + 2) if self.fat[cluster] == 0]
        all_zero = []
        all_ff = []
        nonzero = []
        non_erased = []
        signatures: list[dict] = []
        known = {
            b"\xff\xd8\xff": "JPEG",
            b"II*\x00": "TIFF/DNG little-endian",
            b"MM\x00*": "TIFF/DNG big-endian",
            b"PK\x03\x04": "ZIP",
            b"MZ": "DOS executable",
            b"\x7fELF": "ELF",
        }
        for cluster in free:
            payload = self.cluster_bytes(cluster)
            if not payload.strip(b"\x00"):
                all_zero.append(cluster)
            else:
                nonzero.append(cluster)
            if payload == b"\xff" * len(payload):
                all_ff.append(cluster)
            else:
                non_erased.append(cluster)
            for magic, label in known.items():
                if payload.startswith(magic):
                    signatures.append({"cluster": cluster, "signature": label})
        return {
            "count": len(free),
            "all_zero_count": len(all_zero),
            "nonzero_count": len(nonzero),
            "all_ff_count": len(all_ff),
            "non_erased_count": len(non_erased),
            "all_zero_clusters": all_zero,
            "all_ff_clusters": all_ff,
            "nonzero_clusters": nonzero,
            "non_erased_clusters": non_erased,
            "signatures": signatures,
        }

    def report(self) -> dict:
        fat1 = self.data[self.fat1_offset : self.fat1_offset + self.fat_size]
        fat2 = self.data[self.fat2_offset : self.fat2_offset + self.fat_size]
        active_tree = self.walk_active_tree()
        candidates = self.scan_directory_candidates()
        deleted = [item for item in candidates if item.get("deleted")]
        free_clusters = sum(1 for value in self.fat[2:] if value == 0)
        allocated_clusters = sum(1 for value in self.fat[2:] if value != 0)
        return {
            "image": {
                "path": str(self.path),
                "size": len(self.data),
                "sha256": hashlib.sha256(self.data).hexdigest(),
            },
            "partition": {
                "start_lba": self.partition_lba,
                "sector_count": self.partition_sectors,
                "offset": self.partition_offset,
            },
            "fat16": {
                "bytes_per_sector": self.bytes_per_sector,
                "sectors_per_cluster": self.sectors_per_cluster,
                "cluster_size": self.cluster_size,
                "reserved_sectors": self.reserved_sectors,
                "fat_count": self.fat_count,
                "sectors_per_fat": self.sectors_per_fat,
                "root_entry_count": self.root_entry_count,
                "root_offset": self.root_offset,
                "data_offset": self.data_offset,
                "cluster_count": self.cluster_count,
                "allocated_clusters": allocated_clusters,
                "free_clusters": free_clusters,
                "fat_copies_identical": fat1 == fat2,
                "volume_label": self.volume_label,
                "filesystem_label": self.fs_label,
            },
            "active_tree": active_tree,
            "directory_candidate_count": len(candidates),
            "deleted_directory_entries": deleted,
            "target_hits": self.target_hits(active_tree),
            "free_cluster_inventory": self.free_cluster_inventory(),
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    report = Fat16Image(args.image).report()
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)


if __name__ == "__main__":
    main()
