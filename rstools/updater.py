"""Check GitHub for a newer Train Planning Tools and install it in place (no admin rights needed).

* The latest release is read from the GitHub API. The repository can be public, or private with
  a read-only access token that the user enters once (stored encrypted with Windows DPAPI).
* The new TrainPlanningTools.exe is downloaded next to the running one and checked against the
  SHA-256 digest GitHub publishes for it, so a damaged or tampered download is never used.
* A running exe cannot replace itself on Windows, so a tiny script waits for the app to close,
  swaps the files and starts the new version. If the exe's folder cannot be written to (e.g. a
  read-only share), the new version is saved to Downloads instead.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

REPO = "Albinoboy64/Train-Planning-Tools"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
ASSET = "TrainPlanningTools.exe"
ASSETS = (ASSET, "RollingStockTools.exe")       # the app's name before 3.0.0
TIMEOUT = 20


class UpdateError(Exception):
    pass


@dataclass
class Release:
    version: str
    tag: str
    notes: str
    page: str
    asset_api: str          # API URL of the exe asset (works for private repositories with a token)
    asset_size: int
    digest: str             # 'sha256:...' when GitHub provides it


def version_key(text: str) -> Tuple[int, ...]:
    """'v2.1.4' -> (2, 1, 4); '2.00' -> (2, 0)."""
    return tuple(int(p) for p in re.findall(r"\d+", text or "")) or (0,)


def is_newer(latest: str, current: str) -> bool:
    return version_key(latest) > version_key(current)


# ------------------------------------------------------------------ token storage (Windows DPAPI)
def protect(token: str) -> str:
    if not token:
        return ""
    data = token.encode("utf-8")
    if sys.platform.startswith("win"):
        data = _dpapi(data, encrypt=True)
        return "dpapi:" + base64.b64encode(data).decode("ascii")
    return "plain:" + base64.b64encode(data).decode("ascii")


def unprotect(stored: str) -> str:
    try:
        kind, _sep, payload = (stored or "").partition(":")
        data = base64.b64decode(payload)
        if kind == "dpapi":
            data = _dpapi(data, encrypt=False)
        return data.decode("utf-8") if kind in ("dpapi", "plain") else ""
    except Exception:
        return ""                                   # unreadable (e.g. copied from another PC)


def _dpapi(data: bytes, encrypt: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    src = Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    out = Blob()
    fn = ctypes.windll.crypt32.CryptProtectData if encrypt else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("Windows could not protect the token.")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


# ------------------------------------------------------------------ GitHub
def _request(url: str, token: str = "", accept: str = "application/vnd.github+json") -> urllib.request.Request:
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "TrainPlanningTools-updater",
                                               "X-GitHub-Api-Version": "2022-11-28"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return req


def latest_release(token: str = "") -> Release:
    try:
        with urllib.request.urlopen(_request(API, token), timeout=TIMEOUT) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise UpdateError("GitHub did not allow access to the releases. Check the internet connection; if "
                              "you use a private copy of the repository, add a read-only access token in "
                              f"Options > GitHub access token. (HTTP {exc.code})")
        raise UpdateError(f"GitHub returned an error (HTTP {exc.code}).")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise UpdateError(f"Could not reach GitHub - check the internet connection or proxy. ({exc})")
    try:
        found = {a.get("name"): a for a in data.get("assets", []) if isinstance(a, dict)}
        asset = next((found[n] for n in ASSETS if n in found), None)
        if asset is None:
            raise UpdateError(f"The latest release has no {ASSET} to download.")
        return Release(version=str(data.get("tag_name") or "").lstrip("vV"), tag=str(data.get("tag_name") or ""),
                       notes=str(data.get("body") or "").strip(), page=data.get("html_url") or RELEASES_PAGE,
                       asset_api=str(asset["url"]), asset_size=int(asset.get("size") or 0),
                       digest=str(asset.get("digest") or ""))
    except (AttributeError, KeyError, TypeError, ValueError):     # not the reply GitHub normally sends
        raise UpdateError("GitHub's reply about the latest release could not be read - please try again later.")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def download(rel: Release, dest: str, token: str = "", progress: Callable[[float], None] = lambda f: None) -> str:
    """Download the release's exe to `dest`, verifying its size and SHA-256 digest."""
    opener = urllib.request.build_opener(_NoRedirect)
    req = _request(rel.asset_api, token, accept="application/octet-stream")
    tmp = dest + ".part"
    try:
        try:
            resp = opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as exc:          # GitHub redirects to a signed download link
            if exc.code not in (301, 302, 303, 307, 308):
                raise
            location = exc.headers.get("Location") or ""
            if not location.lower().startswith("https://"):
                raise UpdateError("GitHub sent the download to an address that is not secure (https), so it was "
                                  "not used.")
            # the token is deliberately not sent on: the link is already signed
            resp = urllib.request.urlopen(_request(location, accept="application/octet-stream"), timeout=TIMEOUT)
        sha = hashlib.sha256()
        done = 0
        with resp, open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                if rel.asset_size:
                    progress(min(done / rel.asset_size, 1.0))
    except UpdateError:
        raise
    except Exception as exc:                 # network, disk, or a connection cut mid-download (IncompleteRead)
        try:
            os.remove(tmp)                   # never leave a half-downloaded file behind
        except OSError:
            pass
        raise UpdateError(f"The download failed: {exc}")
    if rel.asset_size and done != rel.asset_size:
        os.remove(tmp)
        raise UpdateError("The download was incomplete - please try again.")
    expected = expected_sha256(rel)
    if not expected:
        os.remove(tmp)
        raise UpdateError("GitHub gave no checksum for this download, so it could not be checked and was not "
                          "used. Download it from the release page instead.")
    if sha.hexdigest() != expected:
        os.remove(tmp)
        raise UpdateError("The downloaded file did not match GitHub's checksum, so it was not used.")
    with open(tmp, "rb") as fh:
        if fh.read(2) != b"MZ":                    # every Windows program starts 'MZ'
            fh.close()
            os.remove(tmp)
            raise UpdateError("The download is not a Windows program, so it was not used.")
    os.replace(tmp, dest)
    return dest


def expected_sha256(rel: Release) -> str:
    """The SHA-256 the download must have: GitHub's own digest of the file, or, for a release made before
    GitHub published digests, the one printed in the release notes. '' if neither is available."""
    if rel.digest.lower().startswith("sha256:"):
        value = rel.digest.split(":", 1)[1].strip().lower()
        if re.fullmatch(r"[0-9a-f]{64}", value):
            return value
    m = re.search(r"SHA-256[^0-9A-Fa-f]{0,40}([0-9A-Fa-f]{64})", rel.notes or "")
    return m.group(1).lower() if m else ""


# ------------------------------------------------------------------ installing
def running_exe() -> Optional[str]:
    """Path of the running exe (None when running from source)."""
    return sys.executable if getattr(sys, "frozen", False) else None


def can_replace_in_place() -> bool:
    exe = running_exe()
    return bool(exe and sys.platform.startswith("win") and os.access(os.path.dirname(exe), os.W_OK))


def download_target(rel: Release) -> str:
    """Where to save the new exe: next to the running one if possible, else Downloads."""
    exe = running_exe()
    if exe and can_replace_in_place():
        return exe + ".new"
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    folder = downloads if os.path.isdir(downloads) else tempfile.gettempdir()
    return os.path.join(folder, f"TrainPlanningTools-{rel.version or 'latest'}.exe")


def _fresh_env() -> dict:
    """Environment for starting the new version as an independent app (not sharing this copy's
    unpacked files, which are removed when it closes)."""
    env = dict(os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)


def install_and_restart(new_exe: str):
    """Put the downloaded exe in place and start it. The caller must quit the app straight after.

    Windows lets a running exe be renamed (not replaced), so the running copy is renamed to '.old',
    the new one moved into its place and started; the '.old' copy is deleted on the next start.
    Where renaming is refused (some network shares), a small script swaps the files after this app
    has closed instead."""
    exe = running_exe()
    if not exe or not sys.platform.startswith("win"):
        raise UpdateError("Updating in place only works for the Windows exe.")
    old = exe + ".old"
    try:
        if os.path.exists(old):
            os.remove(old)
        os.replace(exe, old)
    except OSError:
        return _install_with_script(new_exe, exe)
    try:
        os.replace(new_exe, exe)
    except OSError as exc:
        os.replace(old, exe)                       # put the running version back
        raise UpdateError(f"The new version could not be put in place ({exc}). The current version is "
                          "unchanged.")
    refresh_icons(exe)                             # Explorer, shortcuts and the taskbar show the new logo
    subprocess.Popen([exe], env=_fresh_env(), creationflags=_FLAGS, close_fds=True, cwd=os.path.dirname(exe))


def _cmd_path(path: str) -> str:
    """A path for a .cmd script: '%' doubled so cmd does not expand it as a variable."""
    if '"' in path or "\n" in path or "\r" in path:
        raise UpdateError("The app's folder name cannot be used by the updater - download the new version "
                          "from the release page instead.")
    return path.replace("%", "%%")


def _install_with_script(new_exe: str, exe: str):
    new_exe, exe = _cmd_path(new_exe), _cmd_path(exe)
    fd, script = tempfile.mkstemp(prefix="tpt_update_", suffix=".cmd")     # unique, only this user can write
    os.close(fd)
    with open(script, "w", encoding="mbcs") as fh:
        fh.write("@echo off\r\nset /a tries=0\r\n"                # waits for the app to close (2 minutes at most)
                 f":wait\r\ntasklist /FI \"PID eq {os.getpid()}\" | find \"{os.getpid()}\" >nul || goto swap\r\n"
                 "set /a tries+=1\r\nif %tries% geq 120 goto end\r\n"
                 "timeout /t 1 /nobreak >nul\r\ngoto wait\r\n:swap\r\n"
                 f"move /y \"{new_exe}\" \"{exe}\" >nul\r\n"
                 f"start \"\" \"{exe}\"\r\n"
                 ":end\r\ndel \"%~f0\"\r\n")
    subprocess.Popen(["cmd.exe", "/c", script], env=_fresh_env(), creationflags=_FLAGS, close_fds=True)


def remove_previous_version():
    """Delete the '.old' copy left by an update (quietly retried on later starts if still in use)."""
    exe = running_exe()
    if exe:
        try:
            os.remove(exe + ".old")
        except OSError:
            pass


# ------------------------------------------------------------------ keeping the logo after an update
_SHORTCUT_NAMES = ("train planning", "trainplanning", "rolling stock", "rollingstock", "cwn")


def _shortcut_folders():
    env = os.environ.get
    roaming, home = env("APPDATA", ""), os.path.expanduser("~")
    return [os.path.join(home, "Desktop"), os.path.join(env("PUBLIC", ""), "Desktop") if env("PUBLIC") else "",
            os.path.join(roaming, "Microsoft", "Windows", "Start Menu", "Programs"),
            os.path.join(roaming, "Microsoft", "Internet Explorer", "Quick Launch", "User Pinned", "TaskBar"),
            os.path.join(roaming, "Microsoft", "Internet Explorer", "Quick Launch")]


def refresh_icons(exe: Optional[str] = None):
    """Tell Windows the app's icon may have changed, so Explorer, desktop / Start menu shortcuts and
    pinned taskbar buttons show the logo of the version now installed, not a cached older one (or a
    blank icon). Windows caches icons by file path, and an update keeps the same path."""
    exe = exe or running_exe()
    if not exe or not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        notify = ctypes.windll.shell32.SHChangeNotify
        SHCNE_UPDATEITEM, SHCNE_ASSOCCHANGED, SHCNF_PATHW, SHCNF_IDLIST = 0x2000, 0x08000000, 0x0005, 0x0000
        targets = [exe]
        for folder in _shortcut_folders():
            if not folder or not os.path.isdir(folder):
                continue
            for root, _dirs, files in os.walk(folder):
                targets += [os.path.join(root, f) for f in files
                            if f.lower().endswith(".lnk") and any(n in f.lower() for n in _SHORTCUT_NAMES)]
                if root.count(os.sep) - folder.count(os.sep) >= 2:
                    _dirs[:] = []                    # Start menu: the app's own folder is enough depth
        for path in targets:
            notify(SHCNE_UPDATEITEM, SHCNF_PATHW, ctypes.c_wchar_p(path), None)
        notify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)     # refresh the shell's icon cache
    except Exception:
        pass                                          # cosmetic only: never stop the app starting


def after_start(stamp_file: str):
    """On each start: remove the replaced copy, and when this exe is not the one that ran last time
    (it was updated, by the app or by hand), refresh the icons Windows shows for it."""
    remove_previous_version()
    exe = running_exe()
    if not exe:
        return
    try:
        st = os.stat(exe)
        stamp = f"{os.path.abspath(exe)}|{st.st_size}|{int(st.st_mtime)}"
    except OSError:
        return
    try:
        with open(stamp_file, encoding="utf-8") as fh:
            if fh.read().strip() == stamp:
                return
    except OSError:
        pass
    refresh_icons(exe)
    try:
        with open(stamp_file, "w", encoding="utf-8") as fh:
            fh.write(stamp)
    except OSError:
        pass
