"""'Check for updates' window: finds the latest release on GitHub, downloads and installs it."""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from . import theme, updater


class UpdateDialog(tk.Toplevel):
    def __init__(self, app, current: str, token: str, release: "updater.Release | None" = None):
        super().__init__(app)
        self.app, self.current, self.token = app, current, token
        self.release = release
        self.q: "queue.Queue" = queue.Queue()
        self.title("Check for updates")
        self.transient(app)
        self.resizable(True, True)
        self.minsize(520, 300)
        p = getattr(app, "palette", theme.PALETTES["light"])
        self.configure(background=p["bg"])
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)
        self.head = ttk.Label(body, text="Checking GitHub for a newer version...", style="Head.TLabel")
        self.head.grid(row=0, column=0, sticky="w")
        self.sub = ttk.Label(body, text=f"You have version {current}.", style="Small.TLabel",
                             wraplength=theme.px(body, 480),
                             justify="left")
        self.sub.grid(row=1, column=0, sticky="w", pady=(2, 8))
        self.notes = tk.Text(body, height=10, wrap="word", font="TkTextFont")
        theme.style_text(self.notes, p)
        self.notes.grid(row=2, column=0, sticky="nsew")
        self.prog = ttk.Progressbar(body, mode="indeterminate", maximum=1.0)
        self.prog.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, sticky="e", pady=(10, 0))
        self.install_btn = ttk.Button(buttons, text="Download and install", style="Run.TButton",
                                      command=self._download)
        self.page_btn = ttk.Button(buttons, text="Open release page", command=self._open_page)
        ttk.Button(buttons, text="Close", command=self.destroy).grid(row=0, column=2, padx=(6, 0))
        self.page_btn.grid(row=0, column=1, padx=(6, 0))
        self.install_btn.grid(row=0, column=0)
        self.install_btn.state(["disabled"])
        self.bind("<Escape>", lambda _e: self.destroy())
        self._poll_id = self.after(100, self._poll)
        self.bind("<Destroy>", self._stop, add="+")
        if release:
            self._found(release)
        else:
            self.prog.start(12)
            threading.Thread(target=self._check, daemon=True).start()

    # ----------------------------------------------------------------- work (background threads)
    def _check(self):
        try:
            self.q.put(("found", updater.latest_release(self.token)))
        except updater.UpdateError as exc:
            self.q.put(("error", str(exc)))
        except Exception as exc:                    # anything unexpected still ends the 'Checking...' state
            self.q.put(("error", f"The update check failed: {exc}"))

    def _download(self):
        if any(getattr(t, "running", False) for t in (self.app, self.app.stats_tab, self.app.tt_tab,
                                                       self.app.live_tab)):
            messagebox.showinfo("Check for updates", "Please wait until the current run finishes.", parent=self)
            return
        self.install_btn.state(["disabled"])
        self.prog.stop()
        self.prog.configure(mode="determinate", value=0)
        self.sub.configure(text="Downloading...")
        target = updater.download_target(self.release)

        def work():
            try:
                path = updater.download(self.release, target, self.token, lambda f: self.q.put(("progress", f)))
                self.q.put(("downloaded", path))
            except updater.UpdateError as exc:
                self.q.put(("error", str(exc)))
            except Exception as exc:
                self.q.put(("error", f"The download failed: {exc}"))
        threading.Thread(target=work, daemon=True).start()

    # ----------------------------------------------------------------- results (UI thread)
    def _found(self, rel: "updater.Release"):
        self.release = rel
        self.prog.stop()
        self.prog.configure(mode="determinate", value=0)
        self._set_notes(rel.notes or "(No release notes.)")
        if updater.is_newer(rel.version, self.current):
            self.head.configure(text=f"Version {rel.version} is available")
            how = ("It will be downloaded, checked, and the app will restart on the new version."
                   if updater.can_replace_in_place() else
                   "It will be downloaded to your Downloads folder (this copy's folder cannot be updated "
                   "in place, or the app is running from source).")
            self.sub.configure(text=f"You have version {self.current}. {how}")
            self.install_btn.state(["!disabled"])
        else:
            self.head.configure(text="You have the latest version")
            self.sub.configure(text=f"Version {self.current} is the newest release.")

    def _downloaded(self, path: str):
        self.prog.configure(value=1.0)
        if self.release is not None and updater.can_replace_in_place() \
                and path == updater.download_target(self.release):
            if messagebox.askokcancel("Check for updates", f"Version {self.release.version} is ready.\n\n"
                                      "Train Planning Tools will close, update and reopen.", parent=self):
                self.app.save_app_settings()            # before the new version starts and reads them
                try:
                    updater.install_and_restart(path)
                except (updater.UpdateError, OSError) as exc:
                    messagebox.showerror("Check for updates", str(exc), parent=self)
                    return
                self.app.destroy()
            return
        self.sub.configure(text=f"Saved to {path}")
        messagebox.showinfo("Check for updates", f"The new version was saved to:\n{path}\n\nClose this app and "
                            "run the new file (you can replace your old copy with it).", parent=self)
        try:
            os.startfile(os.path.dirname(path))  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            pass

    def _error(self, text: str):
        self.prog.stop()
        self.prog.configure(mode="determinate", value=0)
        self.head.configure(text="Could not check for updates")
        self.sub.configure(text=text)
        if self.release and updater.is_newer(self.release.version, self.current):
            self.install_btn.state(["!disabled"])

    def _set_notes(self, text: str):
        self.notes.configure(state="normal")
        self.notes.delete("1.0", "end")
        self.notes.insert("end", text)
        self.notes.configure(state="disabled")

    def _open_page(self):
        webbrowser.open(self.release.page if self.release else updater.RELEASES_PAGE)

    def _poll(self):
        try:
            while True:
                kind, value = self.q.get_nowait()
                {"found": self._found, "error": self._error, "downloaded": self._downloaded,
                 "progress": lambda f: self.prog.configure(value=f)}[kind](value)
        except queue.Empty:
            pass
        try:
            if self.winfo_exists():
                self._poll_id = self.after(100, self._poll)
        except tk.TclError:
            pass                                    # the window (or the app) has closed

    def _stop(self, event):
        if event.widget is self:
            try:
                self.after_cancel(self._poll_id)
            except (tk.TclError, ValueError):
                pass
