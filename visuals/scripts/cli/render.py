"""Authored-render engine — serve the web root, drive headless Chrome over
the frame manifest, wait on an explicit readiness signal, capture frames.

Ported from the reference corpus's `_shared/render/render.sh`, whose
load-bearing behaviour is preserved exactly: the server binds a
kernel-allocated port (never a fixed one, never a killed process), the WEB
ROOT (task 0017: declared in visuals.toml, independent of the project root,
so masters can reference shared assets by absolute path) is served, and every
failure is loud and names its cause.

The one deliberate departure is criterion 2: rendering waits on an explicit
readiness signal on `document.documentElement` — `dataset.ready === "true"`
or `dataset.rendered === "true"`, the corpus's own existing convention —
with a real-time deadline, not a fixed virtual-time budget — the corpus's
`--virtual-time-budget=6000` is a timeout masquerading as readiness. The
transport is CDP over `--remote-debugging-pipe` (fd 3/4, NUL-delimited JSON):
stdlib-only, no websocket, no extra dependency.

Three readiness outcomes, exactly as criterion 2 splits them:

- the page implements the signal and fires it in time -> capture; the receipt
  records `readiness: "signal"`;
- the page implements the signal but never fires it -> loud failure naming the
  frame, the attributes polled, and that no value appeared (AC-5: a stuck
  page and a detection error are indistinguishable here, so the message
  asserts neither);
- the page does not implement the signal -> bounded `--virtual-time-budget`
  fallback (the corpus budget); the receipt records `readiness:
  "fallback-budget"`, so the fallback is never silent.

Whether a page implements the signal is decided BEFORE rendering, by a static
scan of the served master and its bounded same-origin scripts for the
documentElement-qualified marker — element-qualified, not a substring scan:
`_shared/source-credit.js` sets `this.dataset.ready` on its own custom
element, which a substring scan matched and then misdiagnosed the whole page
(task 0017 D3).

Task 0005 owns this module. `config.py` (task 0003) and `theme.py` (task 0004)
are consumed lazily inside the functions that need them, with honest
degradation when absent — they are never created here (seam contract).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from store import (
    FrameReceipt,
    VERSION_RE,
    build_receipt,
    chrome_version_of,
    derive_next_version,
    emit_previews,
    repository_state,
    repoint_latest,
    sha256_file,
    stage_and_commit,
    write_receipt,
)

CHROME_CANDIDATES = (
    "google-chrome",
    "chromium",
    "chromium-browser",
    "google-chrome-stable",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
)

DEFAULT_VIEWPORT = (1920, 1080)
DEFAULT_READINESS_TIMEOUT_S = 30.0
DEFAULT_BUDGET_MS = 6000  # the corpus's virtual-time budget, kept as the fallback
LOAD_TIMEOUT_S = 60.0
MANIFEST_NAME = "frames.txt"
SERVER_BOOT_TRIES = 50
SERVER_BOOT_WAIT_S = 0.1
PREVIEW_FALLBACK_WIDTH = 640
MAX_SCANNED_SCRIPTS = 20

# The documentElement readiness contract (task 0017 AC-4), matched on the
# ELEMENT-QUALIFIED expression only. A substring scan for "dataset.ready"
# also matched `_shared/source-credit.js`'s `this.dataset.ready` on its own
# custom element — the page was fine, but render polled an attribute the page
# never sets on documentElement and failed claiming the page was stuck. The
# corpus's existing convention (`dataset.rendered`, index.html:1051) is
# honoured alongside; no third key is invented.
_DOCUMENT_READY_RE = re.compile(
    r"document\s*\.\s*documentElement\s*\.\s*dataset\s*\.\s*(?:ready|rendered)\b"
)
_SCRIPT_SRC_RE = re.compile(r"<script[^>]*\bsrc=[\"']([^\"']+)[\"']", re.I)
_CSS_LINK_RE = re.compile(
    r"<link[^>]*\brel=[\"']stylesheet[\"'][^>]*\bhref=[\"']([^\"']+)[\"']", re.I
)
_ABS_REF_RES = (
    re.compile(r"\b(?:src|href)\s*=\s*[\"'](/[^\"'#?]+)[\"']", re.I),
    re.compile(r"url\(\s*[\"']?(/[^\"')]+)[\"']?\s*\)", re.I),
)
#: Bound on the per-frame asset scan (AC-2): the master plus its local
#: stylesheets, each probed once. A transitive crawl of every referenced
#: asset is a different feature — this scan answers only "would the frame's
#: absolute references resolve under the web root".
MAX_SCANNED_ASSETS = 60


class RenderError(Exception):
    """A blocking render failure. The message names the cause; never a traceback."""


class RenderUnavailable(RenderError):
    """The environment cannot render (e.g. no browser). Exit code 3, not 1."""


# --------------------------------------------------------------------------
# frame manifest — basenames taken from the manifest, normalised (criterion 5)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Frame:
    name: str  # normalised output basename, WITHOUT extension
    url: str  # frame URL relative to the source directory
    requested: str  # the manifest's original basename field
    line: int  # 1-based manifest line, for failure messages


def normalise_basename(raw: str) -> tuple[str, bool]:
    """Strip trailing extensions from a manifest basename; report that we did.

    The `.png.png` defect class (audit F5: five shipped outputs) comes from
    writing an extension into the manifest's basename field. An
    extension-bearing basename is ACCEPTED and normalised, with a warning —
    the defect becomes unconstructable rather than punished. A `.png`
    suffix is stripped repeatedly (any case, the defect class itself); one
    residual extension of any other kind is then stripped once.
    """
    name = raw
    normalised = False
    while name.lower().endswith(".png"):
        name = name[:-4]
        normalised = True
    stem, dot, ext = name.rpartition(".")
    if dot and stem and ext and normalised is False and ext.isalnum():
        name, normalised = stem, True
    if not name or set(name) <= {".", "_", "-"}:
        raise RenderError(f"malformed output name {raw!r} in frame manifest")
    return name, normalised


def parse_manifest(path: Path) -> tuple[list[Frame], list[str]]:
    """Parse the manifest. Fails loudly (criterion 9): a missing manifest and a
    line naming a frame but carrying no URL each name their cause."""
    if not path.is_file():
        raise RenderError(f"no frame manifest at {path}")
    frames: list[Frame] = []
    warnings: list[str] = []
    seen: dict[str, int] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        requested = parts[0]
        if len(parts) != 2 or not parts[1].strip():
            raise RenderError(
                f"manifest line {lineno} in {path} names frame {requested!r} "
                "but has no URL"
            )
        name, changed = normalise_basename(requested)
        if changed:
            warnings.append(
                f"manifest line {lineno}: basename {requested!r} carries an extension; "
                f"normalised to {name!r}"
            )
        if name in seen:
            raise RenderError(
                f"manifest line {lineno}: output name {name!r} duplicates line {seen[name]} "
                "(malformed output name)"
            )
        seen[name] = lineno
        frames.append(Frame(name=name, url=parts[1].strip(), requested=requested, line=lineno))
    if not frames:
        raise RenderError(f"manifest {path} contained no frames")
    return frames, warnings


# --------------------------------------------------------------------------
# locating the visual and the web root
# --------------------------------------------------------------------------


def _load_config(start: Path):
    """Lazily load task 0003's config interface; honest degradation when absent.

    Returns (module, ResolvedConfig | None). A None module means 'not in this
    build' — the receipt records that with `resolution: unavailable`; it never
    means 'invent a project'. A found-but-invalid config is raised loudly.
    """
    try:
        import config  # noqa: PLC0415
    except ImportError:
        return None, None
    try:
        return config, config.resolve_config(start)
    except Exception as exc:
        raise RenderError(f"project config is invalid: {exc}") from exc


def _fallback_web_root(source_dir: Path) -> Path:
    """Without config: nearest ancestor holding visuals.toml, else the source
    directory itself (approved default; recorded in the receipt)."""
    for base in [source_dir.resolve(), *source_dir.resolve().parents]:
        if (base / "visuals.toml").is_file():
            return base
    return source_dir


def locate_visual(slug: str, start: Path, config_resolved) -> tuple[Path, Path, Path]:
    """Return (visual_dir, source_dir, web_root).

    Task 0017 D2: the slug is resolved through `discovery.discover_visuals` —
    the SAME walk `index` and `validate` use — so a visual any command can
    see is a visual every command can see. With a resolved config the project
    root owns the store and the config's web_root is served; without one,
    ancestors of `start` are searched upward (approved fallback). An
    ambiguous slug names every candidate.
    """
    import discovery  # noqa: PLC0415  (shared capability domain — one definition)

    def resolve_under(root: Path) -> Path | None:
        """One visual under `root` matching `slug`: by unique basename (the
        way index/validate name visuals) or by path relative to the root
        (`slug`, or `visuals/<slug>` for the store's own nesting)."""
        root = root.resolve()
        matches = []
        for d in discovery.discover_visuals(root):
            rel = d.relative_to(root).as_posix()
            if d.name == slug or rel == slug or rel == f"visuals/{slug}":
                matches.append(d)
        if len(matches) == 1:
            return matches[0]
        if not matches:
            return None
        raise RenderError(
            f"ambiguous visual {slug!r} under project root {root}: "
            + ", ".join(str(m) for m in matches)
        )

    if config_resolved is not None:
        found = resolve_under(config_resolved.root)
        if found is None:
            raise RenderError(
                f"no visual directory {slug!r} under project root "
                f"{config_resolved.root} — discovery walks the whole tree, so "
                "a visual index or validate can see cannot be unrenderable"
            )
        return found, found / "source", config_resolved.web_root
    for base in [start.resolve(), *start.resolve().parents]:
        found = resolve_under(base)
        if found is not None:
            return found, found / "source", _fallback_web_root(found / "source")
    raise RenderError(
        f"no visual directory {slug!r} found walking up from {start} "
        "(discovery accepts a directory holding a source master or rendered "
        "versions)"
    )


def check_source_under_root(source_dir: Path, web_root: Path) -> None:
    """Criterion 9: a source directory outside the served web root fails loudly."""
    src = source_dir.resolve()
    root = web_root.resolve()
    if src != root and root not in src.parents:
        raise RenderError(
            f"source directory {source_dir} is outside the web root {web_root} "
            "(the web root is served; the source must live under it)"
        )


# --------------------------------------------------------------------------
# browser + server
# --------------------------------------------------------------------------


_SKILL_MD = Path(__file__).resolve().parent.parent.parent / "SKILL.md"


def skill_version() -> str:
    """Read metadata.version from SKILL.md — the one place the version lives.

    Same contract as the dispatcher's read_version, reimplemented here because
    a capability domain must not import the CLI entrypoint. Raises rather than
    returning a placeholder: a provenance field reading "unknown" is exactly
    the worthless commit field the audit called out (F10).
    """
    try:
        text = _SKILL_MD.read_text(encoding="utf-8")
    except OSError as exc:
        raise RenderError(f"cannot read {_SKILL_MD}: {exc}") from None
    fm = re.match(r"^---\n(.*?)\n---", text, re.S)
    if fm:
        in_metadata = False
        for line in fm.group(1).splitlines():
            if re.match(r"^metadata:\s*$", line):
                in_metadata = True
                continue
            if in_metadata:
                if re.match(r"^\S", line):  # left the metadata block
                    break
                vm = re.match(r'^\s+version:\s*["\']?([0-9]+\.[0-9]+\.[0-9]+)', line)
                if vm:
                    return vm.group(1)
    raise RenderError(f"no metadata.version found in {_SKILL_MD}")


def find_chrome() -> str:
    """Corpus-compatible browser discovery: $CHROME, then the usual names."""
    env = os.environ.get("CHROME", "").strip()
    if env:
        if shutil.which(env) or Path(env).is_file():
            return env
        raise RenderUnavailable(f"CHROME={env!r} is not an executable browser")
    for cand in CHROME_CANDIDATES:
        if shutil.which(cand) or Path(cand).is_file():
            return cand
    raise RenderUnavailable(
        "no Chrome/Chromium found (tried: " + ", ".join(CHROME_CANDIDATES)
        + "); set CHROME=/path/to/chrome"
    )


def allocate_port() -> int:
    """A kernel-allocated free port — preserved from render.sh, never guessed."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Server:
    """`python3 -m http.server` on a kernel port, serving the web root."""

    def __init__(self, web_root: Path) -> None:
        self.port = allocate_port()
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(self.port),
             "--bind", "127.0.0.1", "--directory", str(web_root)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(SERVER_BOOT_TRIES):
            try:
                socket.create_connection(("127.0.0.1", self.port), 0.2).close()
                return
            except OSError:
                time.sleep(SERVER_BOOT_WAIT_S)
        self.close()
        raise RenderError(f"local render server on port {self.port} never came up")

    def url(self, src_rel: str, path: str) -> str:
        return f"http://127.0.0.1:{self.port}/{src_rel}/{path.lstrip('/')}"

    def url_for(self, abs_path: str) -> str:
        """URL for a web-root-absolute reference like '/_shared/brand.css'."""
        return f"http://127.0.0.1:{self.port}/{abs_path.lstrip('/')}"

    def serves(self, abs_path: str) -> bool:
        """Does the served web root answer this absolute path? Used by the
        AC-2 scan; never raises (an unreachable server is render's own
        failure elsewhere)."""
        try:
            with urllib.request.urlopen(self.url_for(abs_path), timeout=10) as resp:
                resp.read(1)
            return True
        except OSError:
            return False

    def fetch(self, src_rel: str, path: str) -> bytes:
        try:
            with urllib.request.urlopen(self.url(src_rel, path), timeout=30) as resp:
                return resp.read()
        except OSError as exc:
            raise RenderError(f"could not fetch served file {src_rel}/{path}: {exc}") from exc

    def close(self) -> None:
        self.proc.terminate()


# --------------------------------------------------------------------------
# readiness signal: implement-vs-not is decided before rendering
# --------------------------------------------------------------------------


def _scan_for_markers(text: str) -> bool:
    """The documentElement readiness contract, element-qualified (AC-4).
    Deliberately NOT a substring scan: `this.dataset.ready` on a custom
    element is not this contract."""
    return bool(_DOCUMENT_READY_RE.search(text))


def page_implements_signal(server: _Server, src_rel: str, frame_url: str) -> bool:
    """Does this frame's page implement the documentElement readiness signal
    at all?

    Static scan of the served master plus its bounded same-origin scripts.
    Decided BEFORE rendering so 'implements the signal but never fires it'
    (loud failure naming the frame) is distinguishable from 'does not
    implement it' (bounded-budget fallback, recorded in the receipt).
    """
    html = server.fetch(src_rel, frame_url).decode("utf-8", "replace")
    if _scan_for_markers(html):
        return True
    for count, src in enumerate(_SCRIPT_SRC_RE.findall(html)):
        if count >= MAX_SCANNED_SCRIPTS:
            break
        if src.startswith("data:"):
            continue
        if src.startswith(("http://", "https://", "//")) \
                and "127.0.0.1" not in src and "localhost" not in src:
            continue  # external scripts are outside the render's contract
        try:
            js = server.fetch(src_rel, src).decode("utf-8", "replace")
        except OSError:
            continue
        if _scan_for_markers(js):
            return True
    return False


def _collect_absolute_refs(text: str, into: dict[str, str]) -> None:
    """Collect web-root-absolute references ('/…') from one document into
    `into` keyed by path (dedup), ignoring protocol-relative and external
    absolute URLs (those are outside the render's contract)."""
    for regex in _ABS_REF_RES:
        for ref in regex.findall(text):
            if ref.startswith("//"):
                continue
            into.setdefault(ref, ref)


def unresolved_absolute_references(server: _Server, src_rel: str, frame: Frame) -> list[str]:
    """Absolute references the served web root cannot answer (task 0017 AC-2).

    Bounded: the frame master plus its local stylesheets, each scanned once,
    up to MAX_SCANNED_ASSETS references — a transitive crawl of every asset
    is a different feature. Reports the reference AND the web root it was
    resolved against, because 'brand.css not found' sends someone hunting
    for a missing file when the actual mistake is the wrong web root. Used by
    the render pipeline to emit a loud, NAMED, non-blocking finding (ADR 0004:
    the blocking set stays at four) — a degraded frame must never be silent.
    """
    refs: dict[str, str] = {}
    try:
        html = server.fetch(src_rel, frame.url).decode("utf-8", "replace")
    except RenderError:
        return []  # the frame render itself reports the fetch failure
    _collect_absolute_refs(html, refs)
    for link in _CSS_LINK_RE.findall(html)[:MAX_SCANNED_ASSETS]:
        if link.startswith(("http://", "https://", "//", "data:")):
            continue  # external stylesheets are outside the render's contract
        try:
            css = server.fetch(src_rel, link).decode("utf-8", "replace")
        except RenderError:
            continue  # a missing local stylesheet is caught via the url refs
        _collect_absolute_refs(css, refs)
    return [ref for ref in sorted(refs) if not server.serves(ref)]


def _asset_warning(frame: Frame, ref: str, web_root: Path) -> str:
    return (
        f"absolute reference {ref!r} in frame {frame.name!r} does not resolve "
        f"under web root {web_root.resolve()} — the frame may render degraded "
        "(fallback fonts, missing colours or logos); reported, not blocked (ADR 0004)"
    )


class _Chrome:
    """One headless Chrome process, driven over `--remote-debugging-pipe`.

    Chrome reads commands from fd 3 and writes events to fd 4, NUL-delimited
    JSON — stdlib-only, no websocket. One browser connection serves the whole
    render; each FRAME gets its own target created at its final URL and torn
    down after capture.

    Per-frame targets are load-bearing: navigating a tab across processes
    (about:blank -> http) makes Chrome replace the page target mid-flight, and
    the old CDP session dies nondeterministically ("Session with given id not
    found"). A target created at its final URL never crosses that boundary.
    Session-scoped overrides give the exact canvas viewport — headless=new's
    window includes browser UI, so `--window-size` alone does not yield the
    declared canvas (verified in the task spike).
    """

    def __init__(self, chrome: str) -> None:
        self.binary = chrome  # kept for the budget-fallback invocation
        self._pending: dict[int, dict] = {}
        self._events: list[dict] = []
        self._buf = b""
        self._msg_id = 0
        self._proc: subprocess.Popen | None = None
        self._profile = Path(tempfile.mkdtemp(prefix="visuals-render-"))
        self._launch(chrome)
        self._browser_setup()

    # ---- transport ---------------------------------------------------------

    def _launch(self, chrome: str) -> None:
        to_chrome_r, to_chrome_w = os.pipe()
        from_chrome_r, from_chrome_w = os.pipe()

        def child_setup() -> None:  # renumber so chrome finds its pipe at fds 3/4
            if to_chrome_r != 3:
                os.dup2(to_chrome_r, 3)
                os.close(to_chrome_r)
            if from_chrome_w != 4:
                os.dup2(from_chrome_w, 4)
                os.close(from_chrome_w)

        try:
            self._proc = subprocess.Popen(
                [chrome, "--headless=new", "--no-sandbox", "--disable-gpu",
                 "--hide-scrollbars", "--default-background-color=FFFFFFFF",
                 "--no-first-run", "--disable-extensions",
                 "--disable-component-extensions-with-background-pages",
                 "--disable-background-networking", "--disable-sync",
                 f"--user-data-dir={self._profile}", "--remote-debugging-pipe"],
                pass_fds=(3, 4), preexec_fn=child_setup,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,  # own process group: close() can reap
            )  # stderr must NOT be an undrained PIPE: chrome's noise fills the
            # 64K pipe buffer and blocks the whole browser.
        except OSError as exc:
            raise RenderError(f"chrome could not be launched: {exc}") from exc
        os.close(to_chrome_r)
        os.close(from_chrome_w)
        self._to_chrome_w, self._from_chrome_r = to_chrome_w, from_chrome_r
        os.set_blocking(self._from_chrome_r, False)
        # fresh transport state: a relaunched chrome must not see stale bytes
        self._buf = b""
        self._pending.clear()
        self._events.clear()

    def _pump(self) -> None:
        try:
            chunk = os.read(self._from_chrome_r, 1 << 20)
        except BlockingIOError:
            return
        if not chunk:
            raise RenderError("chrome terminated during the CDP session")
        self._buf += chunk
        while b"\x00" in self._buf:
            raw, self._buf = self._buf.split(b"\x00", 1)
            msg = json.loads(raw)
            if "id" in msg:
                self._pending[msg["id"]] = msg
            else:
                self._events.append(msg)

    def _send(self, method: str, params: dict | None = None,
              session_id: str | None = None) -> int:
        self._msg_id += 1
        msg: dict = {"id": self._msg_id, "method": method, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        os.write(self._to_chrome_w, json.dumps(msg).encode() + b"\x00")
        return self._msg_id

    def _wait_result(self, mid: int, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._pump()
            if mid in self._pending:
                resp = self._pending.pop(mid)
                if "error" in resp:
                    raise RenderError(
                        f"chrome error: {resp['error'].get('message', resp['error'])}"
                    )
                return resp
            time.sleep(0.02)
        raise RenderError(f"chrome did not answer a CDP command within {timeout:g}s")

    def _send_wait(self, method: str, params: dict | None = None,
                   session_id: str | None = None, timeout: float = 30.0) -> dict:
        return self._wait_result(self._send(method, params, session_id), timeout)

    def _browser_setup(self) -> None:
        """Keep flattened auto-attach on: each per-frame target then delivers
        its session as a Target.attachedToTarget event, and wait for startup
        quiescence — headless=new keeps an internal chrome://headless command
        page alive for a moment, and a createTarget issued during that window
        is silently never answered (verified in the task spike)."""
        mid = self._send("Target.setAutoAttach",
                         {"autoAttach": True, "waitForDebuggerOnStart": False,
                          "flatten": True})
    def _browser_setup(self) -> None:
        """Enable flattened auto-attach, then PROVE the transport with a
        throwaway target, relaunching chrome if it never answers.

        headless=new's startup has a nondeterministic window in which a
        createTarget is silently never answered (chrome://headless command
        page settling); observed with identical inputs, so it cannot be waited
        out by clock — it is waited out by proving a round trip works.
        """
        for attempt in range(5):
            mid = self._send("Target.setAutoAttach",
                             {"autoAttach": True, "waitForDebuggerOnStart": False,
                              "flatten": True})
            self._wait_result(mid, 30.0)
            time.sleep(1.0)  # let the startup attach burst finish
            probe = self._send("Target.createTarget", {"url": "about:blank"})
            try:
                target_id, _sid = self._await_session(probe, timeout=6.0)
                self._send("Target.closeTarget", {"targetId": target_id})
                self._pending.clear()
                self._events.clear()
                return
            except RenderError:
                if attempt == 4:
                    raise RenderError(
                        "chrome never accepted a render target over the debugging "
                        "pipe after 5 launches — the environment cannot render"
                    )
                self._kill_tree()  # relaunch fresh
                self._launch(self.binary)
                time.sleep(1.0)

    def _kill_tree(self) -> None:
        """Kill the chrome process group."""
        if self._proc is not None:
            try:
                os.killpg(os.getpgid(self._proc.pid), 9)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass

    def close(self) -> None:
        """Kill chrome AND its whole process tree, then reap promptly.

        Terminating only the parent leaves zygote/gpu/network children alive
        holding memory and profile locks — under a test suite of many renders
        that accumulation alone poisons subsequent launches.
        """
        self._kill_tree()
        shutil.rmtree(self._profile, ignore_errors=True)

    # ---- one frame ----------------------------------------------------------

    def render_frame(
        self, url: str, name: str, width: int, height: int,
        readiness_timeout: float,
    ) -> bytes:
        """One frame end to end: fresh target at its final URL, session
        attached, load waited, readiness polled, screenshot captured, target
        closed. Raises RenderError naming the frame on any failure."""
        create_id = self._send("Target.createTarget", {"url": url})
        self._pending_url = url
        target_id, sid = self._await_session(create_id)
        try:
            self._send_wait("Page.enable", session_id=sid)
            self._send_wait("Runtime.enable", session_id=sid)
            self._send_wait(
                "Emulation.setDeviceMetricsOverride",
                {"width": width, "height": height, "deviceScaleFactor": 1,
                 "mobile": False},
                sid,
            )
            self._wait_load(sid, name, url)
            self._wait_ready(sid, name, url, readiness_timeout)
            self._wait_settled(sid, name, url, readiness_timeout)
            resp = self._send_wait("Page.captureScreenshot", {"format": "png"},
                                   sid, 60.0)
            data = base64.b64decode(resp["result"]["data"])
            if not data:
                raise RenderError(f"empty render for frame {name!r} ({url})")
            return data
        finally:
            self._send("Target.closeTarget", {"targetId": target_id})

    def _await_session(self, create_id: int, timeout: float = 30.0) -> tuple[str, str]:
        """Wait for a created target's session. The attachedToTarget event can
        arrive BEFORE the createTarget ack, so page sessions are retained by
        targetId rather than discarded between iterations."""
        deadline = time.monotonic() + timeout
        target_id: str | None = None
        last_create_sent = time.monotonic()
        page_sessions: dict[str, str] = {}
        while time.monotonic() < deadline:
            self._pump()
            create_resp = self._pending.pop(create_id, None)
            if create_resp is not None:
                if "error" in create_resp:
                    raise RenderError(
                        "chrome error creating the render target: "
                        + str(create_resp["error"].get("message", create_resp["error"]))
                    )
                target_id = create_resp.get("result", {}).get("targetId")
            elif target_id is None and time.monotonic() - last_create_sent > 2.0:
                # headless=new's startup window can swallow a createTarget
                # entirely; retry rather than fail (the old id stays pending,
                # harmless — the ack is ignored when it finally arrives).
                create_id = self._send("Target.createTarget", {"url": self._pending_url})
                last_create_sent = time.monotonic()
            for ev in self._events:
                if ev.get("method") != "Target.attachedToTarget":
                    continue
                info = ev["params"]["targetInfo"]
                if info.get("type") == "page":
                    page_sessions[info["targetId"]] = ev["params"]["sessionId"]
            self._events.clear()
            if target_id is not None and target_id in page_sessions:
                return target_id, page_sessions[target_id]
            time.sleep(0.02)
        raise RenderError("chrome never attached a session for the render target")

    def _wait_load(self, sid: str, name: str, url: str,
                   timeout: float = LOAD_TIMEOUT_S) -> None:
        """Poll document.readyState via Runtime.evaluate.

        An event-driven wait (Page.loadEventFired) loses the race on a warm
        chrome: the load event can be consumed before Page.enable lands on the
        session, hanging the render for the full timeout. readyState polling
        cannot miss a completed load.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            resp = self._send_wait(
                "Runtime.evaluate",
                {"expression": "document.readyState", "returnByValue": True},
                sid, 10.0,
            )
            value = (resp.get("result", {}).get("result", {}) or {}).get("value", "")
            if value == "complete":
                return
            time.sleep(0.05)
        raise RenderError(
            f"frame {name!r} ({url}): page never finished loading within {timeout:g}s"
        )

    def _wait_ready(self, sid: str, name: str, url: str, timeout: float) -> None:
        """Poll the explicit readiness signal; a never-fired signal fails
        loudly naming the frame, the attributes polled, and that no value
        appeared (task 0017 AC-5: the message must let a reader tell a stuck
        page from a detection error, so it asserts neither)."""
        deadline = time.monotonic() + timeout
        # Both keys of the documentElement contract, in one evaluation: the
        # skill's original `ready` and the corpus's existing `rendered` (AC-4).
        expression = (
            "(function(){var d=document.documentElement;"
            "return [d.dataset.ready||'', d.dataset.rendered||''];})()"
        )
        while time.monotonic() < deadline:
            resp = self._send_wait(
                "Runtime.evaluate",
                {"expression": expression, "returnByValue": True},
                sid,
                min(10.0, timeout),
            )
            values = resp.get("result", {}).get("result", {}).get("value", []) or []
            if "true" in values:
                return
            if "error" in values:
                fired = "dataset.rendered" if values.index("error") == 1 else "dataset.ready"
                raise RenderError(
                    f"frame {name!r} ({url}): page signalled readiness error "
                    f"(documentElement.{fired} = 'error')"
                )
            time.sleep(0.05)
        raise RenderError(
            f"frame {name!r} ({url}): the page was detected as implementing the "
            "readiness signal, but no value appeared on either attribute polled "
            "(documentElement.dataset.ready, documentElement.dataset.rendered) "
            f"within {timeout:g}s — the signal was polled and never fired"
        )

    def _wait_settled(self, sid: str, name: str, url: str, timeout: float,
                      settle_cap: float = 10.0) -> None:
        """After the readiness signal fires, wait for the page's declared
        animations/transitions to materialise before capture (task 0017, AC-1
        reproduction).

        The corpus's brand CSS gives progressive-build layers a 240ms opacity
        transition (`brand.css` `.layer`); a capture taken at the moment the
        signal fires is mid-fade and renders partially visible layers that
        the corpus's own settled output does not have. The readiness signal
        marks the content as rendered; the settled wait covers the material-
        isation the signal's author cannot express. Strictly bounded (the
        corpus settle pattern completes in well under a second) so a page
        with an endless animation still captures at the cap. No Chrome flag
        and no budget changes — the invocation is untouched."""
        deadline = time.monotonic() + min(settle_cap, max(timeout, 1.0))
        expression = (
            "(function(){var a=document.getAnimations();"
            "for(var i=0;i<a.length;i++){var s=a[i].playState;"
            "if(s==='running'||s==='pending')return 'busy';}"
            "return 'settled';})()"
        )
        while time.monotonic() < deadline:
            resp = self._send_wait(
                "Runtime.evaluate",
                {"expression": expression, "returnByValue": True},
                sid, 10.0,
            )
            if resp.get("result", {}).get("result", {}).get("value") == "settled":
                return
            time.sleep(0.05)


def budget_render(
    chrome: str, url: str, out_path: Path, width: int, height: int,
    budget_ms: int, name: str,
) -> None:
    """The bounded-budget fallback: the corpus renderer's exact invocation.

    Used only for pages that do not implement the readiness signal; the receipt
    records `readiness: "fallback-budget"` so the fallback path is never silent.
    """
    profile = Path(tempfile.mkdtemp(prefix="visuals-budget-"))
    try:
        proc = subprocess.run(
            [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
             f"--user-data-dir={profile}",
             f"--window-size={width},{height}", "--force-device-scale-factor=1",
             f"--virtual-time-budget={budget_ms}", "--default-background-color=FFFFFFFF",
             f"--screenshot={out_path}", url],
            capture_output=True, text=True, timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        raise RenderError(f"chrome timed out on {url} for frame {name!r}") from exc
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        detail = tail[-1] if tail else f"exit {proc.returncode}"
        raise RenderError(f"chrome failed on {url} for frame {name!r}: {detail}")
    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise RenderError(f"empty render for frame {name!r} ({url})")


# --------------------------------------------------------------------------
# the render pipeline
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RenderOutcome:
    version: str
    version_dir: Path
    receipt: dict
    frames: list[FrameReceipt]
    warnings: list[str]
    deterministic: bool | None  # None = not checked; False = reported non-deterministic


def render_visual(
    *,
    slug: str,
    start: Path,
    level: str = "patch",
    into: str | None = None,
    check: bool = False,
    readiness_timeout: float = DEFAULT_READINESS_TIMEOUT_S,
    budget_ms: int = DEFAULT_BUDGET_MS,
    renderer_version: str = "",
) -> RenderOutcome:
    """Render every frame of a visual's manifest into a new immutable version.

    Pipeline (task 0005): resolve config lazily, locate the visual, parse and
    normalise the manifest, derive the version (an explicit migration target is
    accepted but refused if it exists), render each frame on the readiness
    signal or the bounded-budget fallback (recorded per frame), emit previews
    automatically, write the hashed receipt, commit atomically, and repoint
    `latest` only after every frame succeeded.
    """
    start = Path(start)
    config, config_resolved = _load_config(start)
    visual_dir, source_dir, web_root = locate_visual(slug, start, config_resolved)
    check_source_under_root(source_dir, web_root)
    manifest_path = source_dir / MANIFEST_NAME
    frames, warnings = parse_manifest(manifest_path)

    profile_name: str | None = None
    delivery_scale: float | None = None
    if config_resolved is not None:
        profile = config_resolved.canvas_profiles[config_resolved.default_profile]
        width, height = profile.width, profile.height
        profile_name = profile.name
        delivery_scale = profile.delivery_scale
    else:
        width, height = _env_viewport()
    viewport = f"{width}x{height} @1x"

    src_rel = source_dir.resolve().relative_to(web_root.resolve()).as_posix()
    if into is not None:
        if not VERSION_RE.match(into):
            raise RenderError(f"malformed version {into!r} (expected vX.Y.Z)")
        version = into
    else:
        version = derive_next_version(visual_dir, level)
    if config_resolved is None:
        warnings.append(
            "config resolution unavailable: canvas profile, theme, and project root "
            "resolved by fallback (receipt fields null with resolution 'unavailable')"
        )

    chrome = find_chrome()
    theme_receipt = _resolve_theme_receipt(config, config_resolved)
    # Repository state must be captured BEFORE staging creates untracked
    # artifacts inside the repo — otherwise the render pollutes its own
    # measurement of the source tree (the thing the receipt is about).
    repository = repository_state(web_root)

    outcome: dict = {}

    def builder(staging: Path) -> None:
        asset_warnings: list[str] = []
        frame_receipts = _render_frames(
            web_root=web_root, src_rel=src_rel, frames=frames, out_dir=staging,
            chrome=chrome, width=width, height=height,
            readiness_timeout=readiness_timeout, budget_ms=budget_ms,
            asset_warnings=asset_warnings,
        )
        warnings.extend(asset_warnings)  # AC-2: loud, named, non-blocking
        deterministic: bool | None = None
        if check:
            second = _render_second_pass(
                visual_dir=staging.parent, src_rel=src_rel, frames=frames,
                chrome=chrome, web_root=web_root, width=width, height=height,
                readiness_timeout=readiness_timeout, budget_ms=budget_ms,
            )
            mismatches = [
                f.name for f, s in zip(frame_receipts, second) if f.sha256 != s.sha256
            ]
            deterministic = not mismatches
            outcome["deterministic"] = deterministic
            if mismatches:
                warnings.append(
                    "NON-DETERMINISTIC: frames " + ", ".join(mismatches)
                    + " produced different content hashes across two identical-input "
                    "renders — reported, not silently accepted"
                )
        preview_width = _preview_width(width, delivery_scale)
        sheet_colors = _sheet_colors(config, config_resolved)
        if sheet_colors is None and config_resolved is not None:
            warnings.append(
                "contact sheet uses non-hex defaults (white/black): theme tokens "
                "unavailable for sheet colours"
            )
        emit_previews(staging, [f.name for f in frames], preview_width,
                      colors=sheet_colors)
        receipt = build_receipt(
            rendered_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            source=src_rel,
            manifest=os.path.relpath(manifest_path, staging),
            root_rel=web_root.name,
            canvas_profile=(
                {"name": profile_name, "width": width, "height": height,
                 "delivery_scale": delivery_scale, "resolution": "resolved"}
                if profile_name else
                {"resolution": "unavailable", "width": width, "height": height}
            ),
            viewport=viewport,
            renderer={"engine": "visuals render", "skill": renderer_version or skill_version(),
                      "chrome": chrome_version_of(chrome)},
            repository=repository,
            theme=theme_receipt,
            frames=frame_receipts,
            warnings=warnings,
        )
        write_receipt(staging, receipt)
        outcome["receipt"] = receipt

    stage_and_commit(visual_dir, version, builder)
    repoint_latest(visual_dir, version)
    return RenderOutcome(
        version=version,
        version_dir=visual_dir / version,
        receipt=outcome["receipt"],
        frames=frame_receipts_from(outcome),
        warnings=warnings,
        deterministic=outcome.get("deterministic"),
    )


def frame_receipts_from(outcome: dict) -> list[FrameReceipt]:
    """Per-frame receipts from the committed render, for callers that report them."""
    return [
        FrameReceipt(name=f["name"], bytes_=f["bytes"], sha256=f["sha256"],
                     readiness=f["readiness"])
        for f in outcome["receipt"]["frames"]
    ]


def _render_second_pass(
    *,
    visual_dir: Path,
    src_rel: str,
    frames: list[Frame],
    chrome: str,
    web_root: Path,
    width: int,
    height: int,
    readiness_timeout: float,
    budget_ms: int,
) -> list[FrameReceipt]:
    """Second identical-input pass for the criterion-8 determinism check.

    Lands in a private directory NEXT TO the staging — never inside it, because
    a version directory contains only delivered artifacts — and is removed
    afterwards, including on failure.
    """
    check_dir = visual_dir / f".staging-check-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    check_dir.mkdir(parents=True)
    try:
        return _render_frames(
            web_root=web_root, src_rel=src_rel, frames=frames, out_dir=check_dir,
            chrome=chrome, width=width, height=height,
            readiness_timeout=readiness_timeout, budget_ms=budget_ms,
        )
    finally:
        shutil.rmtree(check_dir, ignore_errors=True)


def _env_viewport() -> tuple[int, int]:
    """Fallback viewport from the render.sh environment contract (RENDER_WIDTH/RENDER_HEIGHT),
    or the corpus default. Used only when config resolution is unavailable."""
    def positive(name: str, default: int) -> int:
        raw = os.environ.get(name, "").strip()
        if not raw:
            return default
        if not raw.isdigit() or int(raw) == 0:
            raise RenderError(f"{name} must be a positive integer, got {raw!r}")
        return int(raw)

    return (positive("RENDER_WIDTH", DEFAULT_VIEWPORT[0]),
            positive("RENDER_HEIGHT", DEFAULT_VIEWPORT[1]))


def _sheet_colors(config, config_resolved) -> dict[str, str] | None:
    """Contact-sheet colours from the resolved theme's background/text roles.

    Hex values only ever come from the theme token vocabulary — never hardcoded
    here. Returns None when the theme is unavailable, letting the store use its
    non-hex mechanical defaults (the fallback is recorded as a warning).
    """
    if config is None or config_resolved is None:
        return None
    try:
        import theme  # noqa: PLC0415  (task 0004's interface, consumed lazily)
    except ImportError:
        return None
    try:
        resolved_theme = theme.resolve_theme(config_resolved.theme, config_resolved)
        flat = theme.flatten_tokens(resolved_theme.tokens)
        background = flat.get("colour.roles.background.surface.hex")
        label = flat.get("colour.roles.text.body.hex")
        if background and label:
            return {"background": background, "label": label}
    except Exception:
        return None
    return None


def _resolve_theme_receipt(config, config_resolved) -> dict:
    """Receipt section for the resolved theme, or honest unavailability.

    The theme module (task 0004) and ResolvedConfig.theme (task 0003) are both
    consumed lazily per the seam contract. The receipt records the theme's name,
    its resolution steps, and a digest of the tokens — never the tokens
    themselves, which would make the receipt a second copy of the theme
    (audit F7).
    """
    if config is None or config_resolved is None:
        return {"resolution": "unavailable",
                "note": "config resolution unavailable; theme not resolvable"}
    try:
        import theme  # noqa: PLC0415  (task 0004's interface, consumed lazily)
    except ImportError:
        return {"resolution": "unavailable",
                "note": "theme resolution module not present in this build"}
    theme_ref = config_resolved.theme  # str name/path or inline Mapping (ruling 2)
    try:
        resolved_theme = theme.resolve_theme(theme_ref, config_resolved)
    except Exception as exc:
        return {"resolution": "unavailable", "note": f"theme could not be resolved: {exc}"}
    tokens_json = json.dumps(resolved_theme.tokens, sort_keys=True, default=str)
    return {
        "name": resolved_theme.name,
        "steps_consulted": list(resolved_theme.steps_consulted),
        "resolution_steps": dict(resolved_theme.resolution_steps),
        "tokens_digest": hashlib.sha256(tokens_json.encode()).hexdigest(),
        "token_count": len(resolved_theme.tokens),
    }


def _render_frames(
    *,
    web_root: Path,
    src_rel: str,
    frames: list[Frame],
    out_dir: Path,
    chrome: str,
    width: int,
    height: int,
    readiness_timeout: float,
    budget_ms: int,
    asset_warnings: list[str] | None = None,
) -> list[FrameReceipt]:
    """Render every frame into `out_dir`; fail loudly naming the frame.

    One Chrome process serves the whole pass; each frame gets its own CDP
    target (created at its final URL) or a bounded-budget fallback shot. The
    CDP chrome launches lazily — a manifest whose frames all take the budget
    fallback never launches one. When `asset_warnings` is given, each frame's
    absolute references are probed against the web root first (task 0017
    AC-2) and every unresolvable one is reported loudly there — the second
    determinism pass omits the scan (identical warnings, already reported).
    """
    server = _Server(web_root)
    holder: list = [None]  # the lazy _Chrome session, closed in finally
    results: list[FrameReceipt] = []
    try:
        if asset_warnings is not None:
            seen: set[str] = set()
            for frame in frames:
                for ref in unresolved_absolute_references(server, src_rel, frame):
                    key = f"{frame.name}\x00{ref}"
                    if key not in seen:
                        seen.add(key)
                        asset_warnings.append(_asset_warning(frame, ref, web_root))
        for frame in frames:
            results.append(_render_frame(
                server=server, frame=frame, src_rel=src_rel, out_dir=out_dir,
                chrome=chrome, session_holder=holder, width=width, height=height,
                readiness_timeout=readiness_timeout, budget_ms=budget_ms,
            ))
        return results
    finally:
        if holder[0] is not None:
            holder[0].close()
        server.close()


def _render_frame(
    *,
    server: _Server,
    frame: Frame,
    src_rel: str,
    out_dir: Path,
    chrome: str,
    session_holder: list,
    width: int,
    height: int,
    readiness_timeout: float,
    budget_ms: int,
) -> FrameReceipt:
    """One frame: decide the readiness path, capture, validate, record.

    Criterion 9's zero-byte condition is checked on BOTH paths; a Chrome error
    or a timeout names the frame and its URL. The CDP chrome is launched
    lazily via `session_holder[0]` — a manifest whose frames all take the
    budget fallback never launches one.
    """
    out_path = out_dir / f"{frame.name}.png"
    if page_implements_signal(server, src_rel, frame.url):
        if session_holder[0] is None:
            session_holder[0] = _Chrome(chrome)
        url = server.url(src_rel, frame.url)
        data = session_holder[0].render_frame(url, frame.name, width, height,
                                              readiness_timeout)
        out_path.write_bytes(data)
        readiness = "signal"
    else:
        budget_render(chrome, server.url(src_rel, frame.url), out_path,
                      width, height, budget_ms, frame.name)
        readiness = "fallback-budget"
    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise RenderError(f"empty render for frame {frame.name!r} ({frame.url})")
    return FrameReceipt(name=f"{frame.name}.png", bytes_=out_path.stat().st_size,
                        sha256=sha256_file(out_path), readiness=readiness)


def _preview_width(width: int, delivery_scale: float | None) -> int:
    """Preview width from the profile's delivery scale; 640 for a 1920 canvas."""
    if delivery_scale:
        return max(1, round(width * delivery_scale))
    return PREVIEW_FALLBACK_WIDTH