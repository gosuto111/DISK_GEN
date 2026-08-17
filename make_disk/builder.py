from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image
from mutagen.id3 import APIC, COMM, ID3, TALB, TPE1, TIT2, TRCK
from mutagen.mp3 import MP3


# Configuration

EMAIL_ADDRESS = "INSERT EMAIL"

TEMPLATE_PATH = Path(__file__).resolve().with_name("template.png")

if getattr(sys, "frozen", False):
    APP_ROOT = Path(sys.executable).resolve().parent
else:
    APP_ROOT = Path(__file__).resolve().parent.parent

DISK_ROOT = APP_ROOT / "DISK"
COMPRESSED_ROOT = APP_ROOT / "COMPRESSED"


MAX_DURATION_SECONDS = 60 * 60
MAX_DISK_BYTES = 128_000_000

DISK_PREFIX = "DISK"
ARTIST_NAME = "NAME"


# Errors

class DiskBuildError(Exception):
    """Expected build failure."""


def fail(message: str) -> None:
    raise DiskBuildError(message)


@dataclass(frozen=True)
class ProgressEvent:
    """Progress information emitted during a disk build."""

    stage: str
    message: str
    fraction: float
    current: int | None = None
    total: int | None = None


ProgressCallback = Callable[[ProgressEvent], None]


def emit_progress(
    callback: ProgressCallback | None,
    *,
    stage: str,
    message: str,
    fraction: float,
    current: int | None = None,
    total: int | None = None,
) -> None:
    if callback is not None:
        callback(
            ProgressEvent(
                stage=stage,
                message=message,
                fraction=max(0.0, min(1.0, fraction)),
                current=current,
                total=total,
            )
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def md5_file(path: Path) -> str:
    digest = hashlib.md5()

    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def parse_phase(value: str) -> str:
    phase = value.strip().upper()

    if not re.fullmatch(r"[A-Z]", phase):
        fail(
            f"Invalid phase '{value}'. "
            f"Phase must be a single letter A-Z."
        )

    return phase


# Disk numbering

def determine_next_disk(phase: str) -> int:
    phase_dir = DISK_ROOT / phase

    if not phase_dir.exists():
        return 1

    if not phase_dir.is_dir():
        fail(f"{phase_dir} exists but is not a directory.")

    numbers = []

    for entry in phase_dir.iterdir():
        if not entry.is_dir():
            fail(f"Unexpected file in phase directory: {entry}")

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
        formatted = ", ".join(f"{number:03d}" for number in numbers)
        fail(
            f"Disk numbering for phase {phase} is not contiguous. "
            f"Found: {formatted}"
        )

    return numbers[-1] + 1


def natural_sort_key(path: Path) -> list[object]:
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", path.name)
    ]


def find_source_tracks(source: Path) -> list[tuple[int, Path]]:
    if not source.exists():
        fail(f"Source directory does not exist: {source}")

    if not source.is_dir():
        fail(f"Source path is not a directory: {source}")

    entries = list(source.iterdir())

    if not entries:
        fail("Source directory is empty.")

    tracks: list[Path] = []

    for entry in entries:
        if not entry.is_file():
            fail(f"Source contains a non-file entry: {entry.name}")

        if entry.suffix.lower() != ".mp3":
            fail(
                f"Source contains a non-MP3 file: {entry.name!r}. "
                f"Only MP3 files are supported."
            )

        tracks.append(entry)

    tracks.sort(key=natural_sort_key)

    return [
        (index, path)
        for index, path in enumerate(tracks, start=1)
    ]


def validate_track_and_get_duration(path: Path) -> float:
    try:
        audio = MP3(path)
        duration = float(audio.info.length)
    except Exception as exc:
        fail(f"Could not read MP3 {path}: {exc}")

    if duration <= 0:
        fail(f"MP3 has invalid duration: {path}")

    return duration


def validate_total_duration(
    tracks: list[tuple[int, Path]],
) -> float:
    total = 0.0

    for _, path in tracks:
        total += validate_track_and_get_duration(path)

    if total >= MAX_DURATION_SECONDS:
        fail(
            f"Combined duration is {total:.3f} seconds. "
            f"Maximum is strictly less than {MAX_DURATION_SECONDS} seconds."
        )

    return total


# Metadata

def strip_metadata(path: Path) -> None:
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
    artist_name: str,
    comment: str,
) -> None:
    tags = ID3()

    tags.add(
        TIT2(
            encoding=3,
            text=[title],
        )
    )

    tags.add(
        TPE1(
            encoding=3,
            text=[artist_name],
        )
    )

    tags.add(
        TALB(
            encoding=3,
            text=[album_name],
        )
    )

    tags.add(
        TRCK(
            encoding=3,
            text=[f"{track_number:02d}"],
        )
    )

    tags.add(
        COMM(
            encoding=3,
            lang="eng",
            desc="",
            text=[comment],
        )
    )

    try:
        tags.save(
            path,
            v2_version=4,
            v1=0,
            padding=lambda size: 0,
        )
    except Exception as exc:
        fail(f"Could not write metadata to {path}: {exc}")


# Tracks

def materialize_tracks(
    source_tracks: list[tuple[int, Path]],
    disk_dir: Path,
    album_name: str,
    artist_name: str,
    comment: str,
    progress_callback: ProgressCallback | None = None,
) -> tuple[list[Path], list[str]]:
    result: list[Path] = []
    track_hashes: list[str] = []

    total = len(source_tracks)

    for index, (track_number, source_path) in enumerate(
        source_tracks,
        start=1,
    ):
        emit_progress(
            progress_callback,
            stage="tracks",
            message=f"Processing track {track_number:02d}",
            fraction=0.375 + (0.25 * (index - 1) / total),
            current=index - 1,
            total=total,
        )

        temporary_path = disk_dir / f"{track_number:02d}.mp3"

        shutil.copy2(
            source_path,
            temporary_path,
        )

        strip_metadata(temporary_path)

        track_hash = sha256_file(temporary_path)

        final_path = (
            disk_dir
            / f"{track_number:02d} - {track_hash}.mp3"
        )

        temporary_path.rename(final_path)

        write_metadata(
            final_path,
            track_number,
            track_hash,
            album_name,
            artist_name,
            comment,
        )

        result.append(final_path)
        track_hashes.append(track_hash)

        print(
            f"  Track {track_number:02d}: "
            f"{track_hash}"
        )

        emit_progress(
            progress_callback,
            stage="tracks",
            message=f"Finished track {track_number:02d}",
            fraction=0.375 + (0.25 * index / total),
            current=index,
            total=total,
        )

    return result, track_hashes


# Cover

def calculate_disk_color(track_hashes: list[str]) -> str:
    digest = hashlib.sha256()

    for track_number, track_hash in enumerate(
        track_hashes,
        start=1,
    ):
        digest.update(track_number.to_bytes(8, "big"))
        digest.update(bytes.fromhex(track_hash))

    return digest.hexdigest()[:6]


def generate_cover(
    template_path: Path,
    output_path: Path,
    color_hex: str,
) -> None:
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
    ).convert("RGB")

    try:
        result.save(
            output_path,
            format="PNG",
            optimize=False,
            compress_level=6,
        )
    except Exception as exc:
        fail(f"Could not save generated cover: {exc}")

    print(f"  Cover color: #{color_hex}")
    print(f"  Cover: {output_path}")


def embed_cover(
    track_paths: list[Path],
    cover_path: Path,
) -> None:
    try:
        cover_data = cover_path.read_bytes()
    except Exception as exc:
        fail(f"Could not read generated cover: {exc}")

    for path in track_paths:
        try:
            tags = ID3(path)
            tags.delall("APIC")

            tags.add(
                APIC(
                    encoding=3,
                    mime="image/png",
                    type=3,
                    desc="",
                    data=cover_data,
                )
            )

            tags.save(path)

        except Exception as exc:
            fail(f"Could not embed cover into {path}: {exc}")

    print(f"  Embedded cover into {len(track_paths)} tracks.")


# Checksums

def generate_checksum_manifests(disk_dir: Path) -> None:
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
        key=lambda path: path.name,
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


# Size

def calculate_disk_size(disk_dir: Path) -> int:
    return sum(
        path.stat().st_size
        for path in disk_dir.rglob("*")
        if path.is_file()
    )


def validate_disk_size(disk_dir: Path) -> int:
    total = calculate_disk_size(disk_dir)

    if total >= MAX_DISK_BYTES:
        fail(
            f"Disk is {total:,} bytes. "
            f"Maximum is strictly less than {MAX_DISK_BYTES:,} bytes."
        )

    return total


# Archive

def verify_archive_tools() -> None:
    if shutil.which("tar") is None:
        fail("GNU tar was not found in PATH.")


def create_archive(
    disk_dir: Path,
    archive_path: Path,
) -> None:
    verify_archive_tools()

    if archive_path.exists():
        fail(f"Archive already exists: {archive_path}")

    command = [
        "tar",
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

        fail(f"tar failed with exit code {exc.returncode}.")

    print(f"  Archive: {archive_path}")


# Build

def build_disk(
    phase: str,
    source_tracks: list[tuple[int, Path]],
    artist_name: str = ARTIST_NAME,
    comment: str = EMAIL_ADDRESS,
    progress_callback: ProgressCallback | None = None,
) -> None:
    emit_progress(
        progress_callback,
        stage="starting",
        message="Starting disk build",
        fraction=0.0,
    )

    phase = parse_phase(phase)

    print()
    print("=== Music Disk Builder ===")
    print()

    disk_number = determine_next_disk(phase)

    disk_id = f"{DISK_PREFIX}_{phase}{disk_number:03d}"

    disk_dir = (
        DISK_ROOT
        / phase
        / f"{disk_number:03d}"
    )

    archive_path = (
        COMPRESSED_ROOT
        / f"{disk_id}.tar"
    )

    print(f"Phase:       {phase}")
    print(f"Disk:        {disk_number:03d}")
    print(f"Disk ID:     {disk_id}")
    print(f"Tracks:      {len(source_tracks)}")
    print()

    print("[1/8] Validating tracks...")

    emit_progress(
        progress_callback,
        stage="validation",
        message="Validating tracks",
        fraction=0.05,
    )

    if not source_tracks:
        fail("Track list is empty.")

    ordered_paths = [
        path
        for _, path in source_tracks
    ]

    source_tracks = [
        (index, path)
        for index, path in enumerate(
            ordered_paths,
            start=1,
        )
    ]

    for number, path in source_tracks:
        if not path.exists():
            fail(f"Track {number:02d} does not exist: {path}")

        if not path.is_file():
            fail(f"Track {number:02d} is not a file: {path}")

        if path.suffix.lower() != ".mp3":
            fail(
                f"Track {number:02d} is not an MP3 file: "
                f"{path.name!r}"
            )

    print(
        f"  Found {len(source_tracks)} track"
        f"{'' if len(source_tracks) == 1 else 's'}."
    )

    emit_progress(
        progress_callback,
        stage="validation",
        message=f"Validated {len(source_tracks)} tracks",
        fraction=0.125,
        current=len(source_tracks),
        total=len(source_tracks),
    )

    emit_progress(
        progress_callback,
        stage="duration",
        message="Checking total duration",
        fraction=0.15,
    )

    print("[2/8] Checking duration...")

    total_duration = validate_total_duration(source_tracks)

    minutes = int(total_duration // 60)
    seconds = total_duration % 60

    print(f"  Total duration: {minutes}:{seconds:06.3f}")

    emit_progress(
        progress_callback,
        stage="duration",
        message="Duration check complete",
        fraction=0.25,
    )

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

    emit_progress(
        progress_callback,
        stage="directory",
        message="Disk directory created",
        fraction=0.30,
    )

    try:
        print("[4/8] Processing tracks...")

        track_paths, track_hashes = materialize_tracks(
            source_tracks,
            disk_dir,
            disk_id,
            artist_name,
            comment,
            progress_callback,
        )

        emit_progress(
            progress_callback,
            stage="cover",
            message="Generating cover",
            fraction=0.65,
        )

        print("[5/8] Generating cover...")

        color_hex = calculate_disk_color(track_hashes)
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

        emit_progress(
            progress_callback,
            stage="cover",
            message="Cover generated and embedded",
            fraction=0.75,
        )

        emit_progress(
            progress_callback,
            stage="checksums",
            message="Generating checksum manifests",
            fraction=0.78,
        )

        print("[6/8] Generating checksum manifests...")

        generate_checksum_manifests(disk_dir)

        emit_progress(
            progress_callback,
            stage="checksums",
            message="Checksum manifests generated",
            fraction=0.85,
        )

        print("[7/8] Checking disk size...")

        disk_size = validate_disk_size(disk_dir)

        emit_progress(
            progress_callback,
            stage="size",
            message=f"Disk size verified: {disk_size:,} bytes",
            fraction=0.90,
        )

        print(
            f"  Disk size: {disk_size:,} bytes "
            f"({disk_size / 1_000_000:.3f} MB)"
        )

        print("[8/8] Creating archive...")

        COMPRESSED_ROOT.mkdir(
            parents=True,
            exist_ok=True,
        )

        emit_progress(
            progress_callback,
            stage="archive",
            message="Creating archive",
            fraction=0.92,
        )

        create_archive(
            disk_dir,
            archive_path,
        )

        emit_progress(
            progress_callback,
            stage="archive",
            message="Archive created",
            fraction=0.99,
        )

    except Exception:
        if disk_dir.exists():
            shutil.rmtree(disk_dir)

        raise

    emit_progress(
        progress_callback,
        stage="complete",
        message="Disk build complete",
        fraction=1.0,
    )

    print()
    print("=== COMPLETE ===")
    print()
    print(f"Disk:    {disk_dir}")
    print(f"Archive: {archive_path}")
    print()
