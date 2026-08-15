#!/usr/bin/env python3
"""Boot a converted GCI in an isolated, muted Dolphin profile.

This harness deliberately does not touch the user's normal Dolphin directory.
Without deterministic input it proves only that the selected game image boots
with the GCI mounted. A timed native-pipe script can drive the GameCube pad
without depending on keyboard focus; a DTM remains the strongest repeatable
input option.
"""

from __future__ import annotations

import argparse
import errno
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tphd_to_gci import quest_log_body_from_gci  # noqa: E402


DEFAULT_DOLPHIN = Path("/Applications/Dolphin.app/Contents/MacOS/Dolphin")
GAME_EXTENSIONS = {".ciso", ".gcm", ".gcz", ".iso", ".rvz", ".tgc", ".wbfs", ".wia"}
PIPE_NAME = "tp-controller"
PIPE_COMMAND = re.compile(
    r"(?:PRESS|RELEASE) (?:A|B|X|Y|Z|START|L|R|D_UP|D_DOWN|D_LEFT|D_RIGHT)"
    r"|SET (?:MAIN|C) [+-]?(?:\d+(?:\.\d*)?|\.\d+) [+-]?(?:\d+(?:\.\d*)?|\.\d+)"
)


def controller_config() -> str:
    """Return a complete Dolphin GCPad mapping for its native pipe backend."""
    return f"""[GCPad1]
Device = Pipe/0/{PIPE_NAME}
Buttons/A = `Button A`
Buttons/B = `Button B`
Buttons/X = `Button X`
Buttons/Y = `Button Y`
Buttons/Z = `Button Z`
Buttons/Start = `Button START`
Main Stick/Up = `Axis MAIN Y +`
Main Stick/Down = `Axis MAIN Y -`
Main Stick/Left = `Axis MAIN X -`
Main Stick/Right = `Axis MAIN X +`
C-Stick/Up = `Axis C Y +`
C-Stick/Down = `Axis C Y -`
C-Stick/Left = `Axis C X -`
C-Stick/Right = `Axis C X +`
Triggers/L = `Button L`
Triggers/R = `Button R`
D-Pad/Up = `Button D_UP`
D-Pad/Down = `Button D_DOWN`
D-Pad/Left = `Button D_LEFT`
D-Pad/Right = `Button D_RIGHT`
"""


def file_monitor_config() -> str:
    """Return Dolphin logging settings that record disc file paths only."""
    return """[Options]
WriteToFile = True
WriteToConsole = False
WriteToWindow = False
Verbosity = 4

[Logs]
FileMon = True
"""


def parse_input_script(path: Path) -> list[tuple[float, str]]:
    """Parse absolute-time native pipe commands from a small text file."""
    commands: list[tuple[float, str]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            timestamp_text, command = line.split(maxsplit=1)
            timestamp = float(timestamp_text)
        except ValueError as error:
            raise ValueError(f"{path}:{line_number}: expected '<seconds> <command>'") from error
        if timestamp < 0:
            raise ValueError(f"{path}:{line_number}: timestamp must not be negative")
        if not PIPE_COMMAND.fullmatch(command):
            raise ValueError(f"{path}:{line_number}: unsupported pipe command {command!r}")
        if commands and timestamp < commands[-1][0]:
            raise ValueError(f"{path}:{line_number}: timestamps must be nondecreasing")
        commands.append((timestamp, command))
    if not commands:
        raise ValueError(f"{path}: input script contains no commands")
    return commands


def write_controller_commands(
    fifo: Path,
    commands: list[tuple[float, str]],
    started: float,
    trace: Path,
    stop: threading.Event,
) -> None:
    """Feed scheduled commands after Dolphin opens the controller FIFO."""
    rows: list[str] = []
    try:
        descriptor = None
        while descriptor is None and not stop.wait(0.05):
            try:
                descriptor = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
            except OSError as error:
                if error.errno != errno.ENXIO:
                    raise
        if descriptor is None:
            rows.append(f"{time.monotonic() - started:.3f} STOP before Dolphin opened controller pipe")
            return
        with os.fdopen(descriptor, "w", encoding="ascii", buffering=1) as stream:
            for timestamp, command in commands:
                delay = started + timestamp - time.monotonic()
                if delay > 0 and stop.wait(delay):
                    rows.append(f"{time.monotonic() - started:.3f} STOP before remaining commands")
                    break
                if stop.is_set():
                    break
                stream.write(command + "\n")
                rows.append(f"{time.monotonic() - started:.3f} {command}")
    except BrokenPipeError:
        rows.append(f"{time.monotonic() - started:.3f} ERROR Dolphin closed controller pipe")
    finally:
        trace.write_text("\n".join(rows) + "\n", encoding="utf-8")


def find_dolphin(explicit: Path | None) -> Path:
    if explicit is not None:
        candidate = explicit
    elif DEFAULT_DOLPHIN.is_file():
        candidate = DEFAULT_DOLPHIN
    else:
        found = shutil.which("dolphin-emu") or shutil.which("Dolphin")
        if found is None:
            raise FileNotFoundError("Dolphin was not found; pass --dolphin /path/to/Dolphin")
        candidate = Path(found)
    if not candidate.is_file():
        raise FileNotFoundError(f"Dolphin executable does not exist: {candidate}")
    return candidate.resolve()


def dolphin_version(executable: Path) -> str:
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return (result.stdout or result.stderr).strip()
    except (subprocess.SubprocessError, OSError):
        info_plist = executable.parents[1] / "Info.plist"
        if info_plist.is_file():
            with info_plist.open("rb") as stream:
                info = plistlib.load(stream)
            version = info.get("CFBundleShortVersionString") or info.get("CFBundleVersion")
            if version:
                return f"Dolphin {version} (from app metadata; executable query unavailable)"
        raise


def validate_inputs(game: Path, gci: Path, movie: Path | None) -> None:
    if not game.is_file():
        raise FileNotFoundError(f"Game image does not exist: {game}")
    if game.suffix.lower() not in GAME_EXTENSIONS:
        raise ValueError(f"Unsupported game image extension {game.suffix!r}")
    if not gci.is_file():
        raise FileNotFoundError(f"GCI does not exist: {gci}")
    quest_log_body_from_gci(gci.read_bytes(), 0)
    if movie is not None and not movie.is_file():
        raise FileNotFoundError(f"Dolphin input movie does not exist: {movie}")


def run_dolphin(
    executable: Path,
    game: Path,
    gci: Path,
    movie: Path | None,
    input_script: Path | None,
    expect_disc_path: str | None,
    video_backend: str,
    timeout_seconds: float,
    artifacts: Path,
) -> int:
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tphd-dolphin-") as directory:
        user_dir = Path(directory) / "User"
        gci_dir = user_dir / "GC" / "USA" / "Card A"
        gci_dir.mkdir(parents=True)
        shutil.copy2(gci, gci_dir / "01-GZ2E-gczelda2.gci")

        commands: list[tuple[float, str]] | None = None
        if input_script is not None:
            commands = parse_input_script(input_script)
            config_dir = user_dir / "Config"
            pipe_dir = user_dir / "Pipes"
            config_dir.mkdir(parents=True)
            pipe_dir.mkdir(parents=True)
            (config_dir / "GCPadNew.ini").write_text(controller_config(), encoding="utf-8")
            os.mkfifo(pipe_dir / PIPE_NAME)
        if expect_disc_path is not None:
            config_dir = user_dir / "Config"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "Logger.ini").write_text(file_monitor_config(), encoding="utf-8")

        command = [
            str(executable),
            "--batch",
            f"--user={user_dir}",
            f"--exec={game.resolve()}",
            f"--video_backend={video_backend}",
            "--audio_emulation=HLE",
            "--config=Dolphin.Core.SlotA=8",
            f"--config=Dolphin.Core.GCIFolderAPathOverride={gci_dir}",
            "--config=Dolphin.Core.ConfirmStop=False",
            "--config=Dolphin.DSP.Volume=0",
            "--config=Dolphin.Input.BackgroundInput=True",
        ]
        if movie is not None:
            command.append(f"--movie={movie.resolve()}")

        started = time.monotonic()
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        controller_thread = None
        controller_stop = threading.Event()
        if commands is not None:
            controller_thread = threading.Thread(
                target=write_controller_commands,
                args=(
                    user_dir / "Pipes" / PIPE_NAME,
                    commands,
                    started,
                    artifacts / "controller-trace.log",
                    controller_stop,
                ),
            )
            controller_thread.start()
        timed_out = False
        try:
            output, _ = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.terminate()
            try:
                output, _ = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                output, _ = process.communicate()

        if controller_thread is not None:
            controller_stop.set()
            controller_thread.join(timeout=2)
            if controller_thread.is_alive():
                raise RuntimeError("controller pipe thread did not stop")

        elapsed = time.monotonic() - started
        (artifacts / "dolphin-output.log").write_text(output, encoding="utf-8")
        (artifacts / "command.txt").write_text("\n".join(command) + "\n", encoding="utf-8")
        monitored_paths = user_dir / "Logs" / "dolphin.log"
        monitor_output = ""
        if monitored_paths.is_file():
            monitor_output = monitored_paths.read_text(encoding="utf-8", errors="replace")
            (artifacts / "disc-paths.log").write_text(monitor_output, encoding="utf-8")
        print(f"Dolphin runtime: {elapsed:.1f}s")
        print(f"Timed run completed: {timed_out}")
        print(f"Process exit code: {process.returncode}")
        print(f"Artifacts: {artifacts.resolve()}")

        if not timed_out and process.returncode != 0:
            print(output[-4000:], file=sys.stderr)
            return 1
        if expect_disc_path is not None:
            if expect_disc_path not in monitor_output:
                print(f"Expected disc path was not observed: {expect_disc_path!r}", file=sys.stderr)
                return 1
            print(f"Expected disc path observed: {expect_disc_path!r}")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dolphin", type=Path, help="Dolphin executable; auto-detected by default")
    parser.add_argument("--self-check", action="store_true", help="Only verify that Dolphin can be found and queried")
    parser.add_argument("--game", type=Path, help="Legally dumped Twilight Princess GameCube image")
    parser.add_argument("--gci", type=Path, help="Converted GCI to mount in isolated slot A")
    parser.add_argument("--movie", type=Path, help="Optional deterministic Dolphin DTM input movie")
    parser.add_argument(
        "--input-script",
        type=Path,
        help="Timed native controller commands ('<seconds> PRESS A', etc.); independent of keyboard focus",
    )
    parser.add_argument(
        "--expect-disc-path",
        help="Enable Dolphin's file monitor and fail unless this exact substring is loaded",
    )
    parser.add_argument(
        "--video-backend",
        default="Null",
        choices=("Null", "Metal", "OGL", "Vulkan", "Software Renderer"),
        help="Dolphin video backend (default: Null)",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="Maximum emulation time in seconds (default: 30)")
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts/dolphin-smoke"))
    args = parser.parse_args()

    executable = find_dolphin(args.dolphin)
    print(f"Dolphin executable: {executable}")
    print(f"Dolphin version: {dolphin_version(executable)}")
    if args.self_check:
        return
    if args.game is None or args.gci is None:
        parser.error("--game and --gci are required unless --self-check is used")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    validate_inputs(args.game, args.gci, args.movie)
    if args.input_script is not None and not args.input_script.is_file():
        parser.error(f"input script does not exist: {args.input_script}")
    raise SystemExit(
        run_dolphin(
            executable,
            args.game,
            args.gci,
            args.movie,
            args.input_script,
            args.expect_disc_path,
            args.video_backend,
            args.timeout,
            args.artifacts,
        )
    )


if __name__ == "__main__":
    main()
