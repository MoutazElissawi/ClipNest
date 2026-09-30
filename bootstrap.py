"""Install official OBS runtime libraries into ClipNest's private data folder."""
import hashlib
import os
from pathlib import Path
import shutil
import sys
import urllib.request
import zipfile

from clipnest.config import DATA, ENGINE

OBS_VERSION = "32.2.2"
OBS_URL = f"https://github.com/obsproject/obs-studio/releases/download/{OBS_VERSION}/OBS-Studio-{OBS_VERSION}-Windows-x64.zip"
OBS_SHA256 = "4d6e40e3ab155f56b30de517380566a206d74b63cdf5ad49aa596924768f97e1"


def setup():
    import struct
    if struct.calcsize("P") != 8:
        raise RuntimeError("Install 64-bit Python. The recorder libraries are Windows x64.")
    if os.name != "nt":
        raise RuntimeError("ClipNest capture requires Windows 10/11 x64.")
    marker = ENGINE / "clipnest-engine-version.txt"
    required = ["bin/64bit/obs.dll", "bin/64bit/libobs-d3d11.dll", "bin/64bit/obs-ffmpeg-mux.exe", "bin/64bit/obs-nvenc-test.exe",
                "obs-plugins/64bit/win-capture.dll", "obs-plugins/64bit/win-wasapi.dll",
                "obs-plugins/64bit/obs-ffmpeg.dll", "obs-plugins/64bit/obs-nvenc.dll", "obs-plugins/64bit/obs-x264.dll"]
    if marker.exists() and marker.read_text().strip() == OBS_VERSION and all((ENGINE / name).exists() for name in required):
        return
    DATA.mkdir(parents=True, exist_ok=True)
    archive = DATA / "obs-download.zip"
    temp = DATA / "engine-installing"
    print(f"Downloading official OBS runtime {OBS_VERSION} for ClipNest.", flush=True)
    print("This first-time download can take several minutes. Existing OBS installs are not changed.", flush=True)
    request = urllib.request.Request(OBS_URL, headers={"User-Agent": "ClipNest-Setup/0.1"})
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as target:
        total, done, last = int(response.headers.get("Content-Length", 0)), 0, -1
        while chunk := response.read(1024 * 1024):
            target.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            progress = int(done / total * 100) if total else done // (1024 * 1024)
            if progress != last:
                print(f"\rDownload: {progress}{'%' if total else ' MiB'}", end="", flush=True)
                last = progress
    print("\nVerifying download...", flush=True)
    if digest.hexdigest() != OBS_SHA256:
        archive.unlink(missing_ok=True)
        raise RuntimeError("The recorder download did not match its published SHA-256. Please rerun setup.")
    if temp.exists():
        shutil.rmtree(temp)
    temp.mkdir()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            if not (temp / member.filename).resolve().is_relative_to(temp.resolve()):
                raise RuntimeError("The recorder archive contains an invalid path.")
        bundle.extractall(temp)
    if not (temp / "bin/64bit/obs.dll").exists():
        raise RuntimeError("Unexpected recorder archive layout. Installation was not activated.")
    if ENGINE.exists():
        # Preserve any earlier partial setup/configuration; never remove user clips.
        shutil.copytree(temp, ENGINE, dirs_exist_ok=True)
        shutil.rmtree(temp)
    else:
        temp.rename(ENGINE)
    (ENGINE / "portable_mode.txt").touch()
    (ENGINE / "clipnest-engine-version.txt").write_text(OBS_VERSION)
    archive.unlink(missing_ok=True)
    print("Native recorder libraries ready. ClipNest does not launch OBS Studio.", flush=True)


if __name__ == "__main__":
    try:
        setup()
    except Exception as exc:
        print(f"\nSetup failed: {exc}", file=sys.stderr)
        sys.exit(1)
