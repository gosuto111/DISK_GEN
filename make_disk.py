#!/usr/bin/env python3

"""
Music Disk Builder

Builds a standardized disk from a numbered sequence of MP3 files.

Runtime:
    ./make_disk.py --phase A --source ./SOURCE

Expected source:
    SOURCE/
    ├── 01.mp3
    ├── 02.mp3
    ├── 03.mp3
    └── ...

Produces:
    DISK/<PHASE>/<NUMBER>/
        01 - <sha256>.mp3
        02 - <sha256>.mp3
        ...
        cover.png
        checksums.md5
        checksums.sha256

And:
    COMPRESSED/DISK_<PHASE><NUMBER>.tar.zst
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image
from mutagen.id3 import (
    APIC,
    COMM,
    TALB,
    TPE1,
    TIT2,
    TRCK,
    ID3,
)
from mutagen.mp3 import MP3


# global

# email
EMAIL_ADDRESS = "0x91CC8963@proton.me"

# template
TEMPLATE_PATH = Path("template.png")

# data dir
DISK_ROOT = Path("DISK")

# archive dir
COMPRESSED_ROOT = Path("COMPRESSED")

# constraints
MAX_DURATION_SECONDS = 60 * 60
MAX_DISK_BYTES = 128_000_000  # 128 MB, decimal.

# Disk naming.
DISK_PREFIX = "DISK"

# Artist.
ARTIST_NAME = "エーフィ…？"


# error

class DiskBuildError(Exception):
    """Expected build failure."""


# helpers

def fail(message: str) -> None:
    raise DiskBuildError(message)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def md5_file(path: Path) -> str:
    """Return the MD5 digest of a file."""
    digest = hashlib.md5()

    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def parse_phase(value: str) -> str:
    """
    Validate and normalize a phase name.

    Phases are currently represented by a single ASCII letter.
    """
    phase = value.strip().upper()

    if not re.fullmatch(r"[A-Z]", phase):
        fail(f"Invalid phase '{value}'. Phase must be a single letter A-Z.")

    return phase


# numbering

def determine_next_disk(phase: str) -> int:
    """
    Determine the next disk number for a phase.

    Existing phase directories must form a contiguous sequence beginning
    at 001. Gaps are treated as an integrity error.
    """
    phase_dir = DISK_ROOT / phase

    if not phase_dir.exists():
        return 1

    if not phase_dir.is_dir():
        fail(f"{phase_dir} exists but is not a directory.")

    numbers = []

    for entry in phase_dir.iterdir():
        if not entry.is_dir():
            fail(
                f"Unexpected file in phase directory: {entry}"
            )

        if not re.fullmatch(r"\d{3}", entry.name):
            fail(
                f"Unexpected directory in phase directory: "
                f"{entry.name!r}. Expected a three-digit disk number."
            )

        numbers.append(int(entry.name))

    if not numbers:
        return 1

    numbers.sort()

    expected = list(range(1, len(numbers) + 1))

    if numbers != expected:
        formatted = ", ".join(f"{n:03d}" for n in numbers)
        fail(
            f"Disk numbering for phase {phase} is not contiguous. "
            f"Found: {formatted}"
        )

    return numbers[-1] + 1


# validation

TRACK_FILENAME_RE = re.compile(r"^(\d{2})\.mp3$", re.IGNORECASE)


def find_source_tracks(source: Path) -> list[tuple[int, Path]]:
    """
    Validate the source directory and return tracks in numerical order.
    """
    if not source.exists():
        fail(f"Source directory does not exist: {source}")

    if not source.is_dir():
        fail(f"Source path is not a directory: {source}")

    entries = list(source.iterdir())

    if not entries:
        fail("Source directory is empty.")

    tracks: list[tuple[int, Path]] = []

    for entry in entries:
        if not entry.is_file():
            fail(f"Source contains a non-file entry: {entry.name}")

        match = TRACK_FILENAME_RE.fullmatch(entry.name)

        if not match:
            fail(
                f"Invalid source filename: {entry.name!r}. "
                f"Expected names such as 01.mp3, 02.mp3, etc."
            )

        number = int(match.group(1))
        tracks.append((number, entry))

    tracks.sort(key=lambda item: item[0])

    expected = list(range(1, len(tracks) + 1))
    actual = [number for number, _ in tracks]

    if actual != expected:
        fail(
            "Source track numbering is not contiguous. "
            f"Expected {expected}, found {actual}."
        )

    return tracks


def validate_track_and_get_duration(path: Path) -> float:
    """
    Validate that an MP3 can be parsed and return its duration.
    """
    try:
        audio = MP3(path)
        duration = float(audio.info.length)
    except Exception as exc:
        fail(f"Could not read MP3 {path}: {exc}")

    if duration <= 0:
        fail(f"MP3 has invalid duration: {path}")

    return duration


def validate_total_duration(
    tracks: list[tuple[int, Path]]
) -> float:
    """
    Ensure the complete source is strictly shorter than one hour.
    """
    total = 0.0

    for _, path in tracks:
        total += validate_track_and_get_duration(path)

    if total >= MAX_DURATION_SECONDS:
        fail(
            f"Combined duration is {total:.3f} seconds. "
            f"Maximum is strictly less than "
            f"{MAX_DURATION_SECONDS} seconds."
        )

    return total


# normalization / metadata

def strip_metadata(path: Path) -> None:
    """
    Remove existing ID3 metadata without transcoding the MP3.
    """
    try:
        audio = MP3(path)

        if audio.tags is not None:
            audio.delete()

    except Exception as exc:
        fail(f"Could not strip metadata from {path}: {exc}")


def write_metadata(
    path: Path,
    track_number: int,
    title: str,
    album_name: str,
) -> None:
    """
    Replace the file's metadata with the minimal disk metadata.
    """
    tags = ID3()

    tags.add(TIT2(
        encoding=3,
        text=[title],
    ))

    tags.add(TPE1(
        encoding=3,
        text=[ARTIST_NAME],
    ))

    tags.add(TALB(
        encoding=3,
        text=[album_name],
    ))

    tags.add(TRCK(
        encoding=3,
        text=[f"{track_number:02d}"],
    ))

    tags.add(COMM(
        encoding=3,
        lang="eng",
        desc="",
        text=[EMAIL_ADDRESS],
    ))

    try:
        tags.save(path)
    except Exception as exc:
        fail(f"Could not write metadata to {path}: {exc}")


# materialization

def materialize_tracks(
    source_tracks: list[tuple[int, Path]],
    disk_dir: Path,
    album_name: str,
) -> list[Path]:
    """
    Copy, strip metadata, hash, rename, and write metadata for each track.
    """
    result: list[Path] = []

    for track_number, source_path in source_tracks:
        # Temporary filename preserves the original numbered identity while
        # metadata is removed.
        temporary_path = disk_dir / f"{track_number:02d}.mp3"

        shutil.copy2(source_path, temporary_path)

        # Remove all source metadata first.
        strip_metadata(temporary_path)

        # Hash the normalized MP3. This prevents source metadata from
        # affecting the track's identity.
        track_hash = sha256_file(temporary_path)

        final_path = (
            disk_dir
            / f"{track_number:02d} - {track_hash}.mp3"
        )

        temporary_path.rename(final_path)

        # The title is the same SHA-256 used in the filename.
        write_metadata(
            final_path,
            track_number,
            track_hash,
            album_name,
        )

        result.append(final_path)

        print(
            f"  Track {track_number:02d}: "
            f"{track_hash}"
        )

    return result


# cover color

def calculate_disk_color(track_paths: list[Path]) -> str:
    """
    Produce a deterministic color from the finalized pre-cover disk state.

    The canonical input consists of:
        filename
        filename length
        file contents

    Tracks are sorted by filename so filesystem ordering cannot influence
    the result.

    The generated color is the first six hexadecimal characters of the
    resulting SHA-256 digest.
    """
    digest = hashlib.sha256()

    for path in sorted(track_paths, key=lambda p: p.name):
        filename = path.name.encode("utf-8")
        file_size = path.stat().st_size

        digest.update(
            len(filename).to_bytes(8, "big")
        )
        digest.update(filename)

        digest.update(
            file_size.to_bytes(8, "big")
        )

        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)

    return digest.hexdigest()[:6]


# cover generation

def generate_cover(
    template_path: Path,
    output_path: Path,
    color_hex: str,
) -> None:
    """
    Fill the template's transparent areas with the generated color by
    compositing the template over a solid-color background, then flatten
    the result into an opaque RGB PNG.
    """
    if not template_path.exists():
        fail(f"Cover template does not exist: {template_path}")

    try:
        template = Image.open(template_path).convert("RGBA")
    except Exception as exc:
        fail(f"Could not open cover template: {exc}")

    color = tuple(
        int(color_hex[i:i + 2], 16)
        for i in (0, 2, 4)
    )

    background = Image.new(
        "RGBA",
        template.size,
        color + (255,),
    )

    result = Image.alpha_composite(
        background,
        template,
    )

    # Flatten to one stable, opaque image.
    result = result.convert("RGB")

    try:
        result.save(
            output_path,
            format="PNG",
            optimize=False,
        )
    except Exception as exc:
        fail(f"Could not save generated cover: {exc}")

    print(f"  Cover color: #{color_hex}")
    print(f"  Cover: {output_path}")


# cover embedding

def embed_cover(
    track_paths: list[Path],
    cover_path: Path,
) -> None:
    """
    Embed the exact generated cover.png into every MP3.
    """
    try:
        cover_data = cover_path.read_bytes()
    except Exception as exc:
        fail(f"Could not read generated cover: {exc}")

    for path in track_paths:
        try:
            tags = ID3(path)

            # Remove any existing artwork just in case.
            tags.delall("APIC")

            tags.add(APIC(
                encoding=3,
                mime="image/png",
                type=3,  # Front cover.
                desc="",
                data=cover_data,
            ))

            tags.save(path)

        except Exception as exc:
            fail(f"Could not embed cover into {path}: {exc}")

    print(f"  Embedded cover into {len(track_paths)} tracks.")


# checksum manifests

def generate_checksum_manifests(disk_dir: Path) -> None:
    """
    Generate MD5 and SHA-256 manifests for the completed disk files.

    The manifest files themselves are excluded from their own manifests.
    """
    files = sorted(
        (
            path
            for path in disk_dir.iterdir()
            if path.is_file()
            and path.name not in {
                "checksums.md5",
                "checksums.sha256",
            }
        ),
        key=lambda p: p.name,
    )

    md5_lines = []
    sha256_lines = []

    for path in files:
        md5_lines.append(
            f"{md5_file(path)}  {path.name}"
        )

        sha256_lines.append(
            f"{sha256_file(path)}  {path.name}"
        )

    (disk_dir / "checksums.md5").write_text(
        "\n".join(md5_lines) + "\n",
        encoding="utf-8",
    )

    (disk_dir / "checksums.sha256").write_text(
        "\n".join(sha256_lines) + "\n",
        encoding="utf-8",
    )

    print("  Generated checksum manifests.")


# size check

def calculate_disk_size(disk_dir: Path) -> int:
    """
    Calculate the total size of all files directly contained in the disk.
    """
    return sum(
        path.stat().st_size
        for path in disk_dir.rglob("*")
        if path.is_file()
    )


def validate_disk_size(disk_dir: Path) -> int:
    """
    Ensure the completed disk is strictly smaller than 128 MB.
    """
    total = calculate_disk_size(disk_dir)

    if total >= MAX_DISK_BYTES:
        fail(
            f"Disk is {total:,} bytes. "
            f"Maximum is strictly less than {MAX_DISK_BYTES:,} bytes."
        )

    return total


# archiving

def verify_archive_tools() -> None:
    """
    Verify that GNU tar and zstd are available.
    """
    if shutil.which("tar") is None:
        fail("GNU tar was not found in PATH.")

    if shutil.which("zstd") is None:
        fail("zstd was not found in PATH.")


def create_archive(
    disk_dir: Path,
    archive_path: Path,
) -> None:
    """
    Archive the disk's contents directly.

    The disk directory itself is NOT added as a containing directory.
    """
    verify_archive_tools()

    if archive_path.exists():
        fail(f"Archive already exists: {archive_path}")

    command = [
        "tar",
        "--zstd",
        "-cf",
        str(archive_path.resolve()),
        "-C",
        str(disk_dir.resolve()),
        ".",
    ]

    try:
        subprocess.run(
            command,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        if archive_path.exists():
            archive_path.unlink()

        fail(
            f"tar/zstd failed with exit code {exc.returncode}."
        )

    print(f"  Archive: {archive_path}")


# main build

def build_disk(phase: str, source: Path) -> None:
    phase = parse_phase(phase)

    print()
    print("=== Music Disk Builder ===")
    print()

    # determine disk number

    disk_number = determine_next_disk(phase)

    disk_id = f"{DISK_PREFIX}_{phase}{disk_number:03d}"

    disk_dir = (
        DISK_ROOT
        / phase
        / f"{disk_number:03d}"
    )

    archive_path = (
        COMPRESSED_ROOT
        / f"{disk_id}.tar.zst"
    )

    print(f"Phase:       {phase}")
    print(f"Disk:        {disk_number:03d}")
    print(f"Disk ID:     {disk_id}")
    print(f"Source:      {source}")
    print()

    # validate

    print("[1/8] Validating source...")

    source_tracks = find_source_tracks(source)

    print(
        f"  Found {len(source_tracks)} track"
        f"{'' if len(source_tracks) == 1 else 's'}."
    )

    # duration check

    print("[2/8] Checking duration...")

    total_duration = validate_total_duration(source_tracks)

    minutes = int(total_duration // 60)
    seconds = total_duration % 60

    print(
        f"  Total duration: {minutes}:{seconds:06.3f}"
    )

    # disk directory

    print("[3/8] Creating disk directory...")

    if disk_dir.exists():
        fail(
            f"Refusing to overwrite existing disk directory: "
            f"{disk_dir}"
        )

    disk_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    print(f"  Created: {disk_dir}")

    try:
        # processing
        
        print("[4/8] Processing tracks...")

        track_paths = materialize_tracks(
            source_tracks,
            disk_dir,
            disk_id,
        )

        # cover generation
        
        print("[5/8] Generating cover...")

        color_hex = calculate_disk_color(track_paths)

        cover_path = disk_dir / "cover.png"

        generate_cover(
            TEMPLATE_PATH,
            cover_path,
            color_hex,
        )

        embed_cover(
            track_paths,
            cover_path,
        )

        # generate checksums
        
        print("[6/8] Generating checksum manifests...")

        generate_checksum_manifests(disk_dir)

        print("[7/8] Checking disk size...")

        disk_size = validate_disk_size(disk_dir)

        print(
            f"  Disk size: {disk_size:,} bytes "
            f"({disk_size / 1_000_000:.3f} MB)"
        )

        # archive
        
        print("[8/8] Creating archive...")

        COMPRESSED_ROOT.mkdir(
            parents=True,
            exist_ok=True,
        )

        create_archive(
            disk_dir,
            archive_path,
        )

    except Exception:
        # If construction fails, remove the incomplete disk rather than
        # leaving a seemingly valid but unfinished disk behind.
        if disk_dir.exists():
            shutil.rmtree(disk_dir)

        raise

    print()
    print("=== COMPLETE ===")
    print()
    print(f"Disk:    {disk_dir}")
    print(f"Archive: {archive_path}")
    print()


# CLI

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a standardized music disk."
    )

    parser.add_argument(
        "--phase",
        required=True,
        help="Phase letter, e.g. A",
    )

    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Directory containing 01.mp3, 02.mp3, etc.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        build_disk(
            args.phase,
            args.source,
        )

    except DiskBuildError as exc:
        print(
            f"\nERROR: {exc}",
            file=sys.stderr,
        )
        return 1

    except KeyboardInterrupt:
        print(
            "\nERROR: Interrupted.",
            file=sys.stderr,
        )
        return 130

    except Exception as exc:
        print(
            f"\nUNEXPECTED ERROR: {exc}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
