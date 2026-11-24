"""Standalone desktop launcher for SPECiT (Windows .exe and macOS .app / .dmg)."""

from __future__ import annotations

import argparse
import os
import platform
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from engine.version import APP_NAME, APP_STAGE, APP_VERSION, default_workspace_root


def _augment_path_for_gui_app() -> None:
    """When launched from macOS Finder (.app), PATH lacks Homebrew/npm/user bins needed for AI CLIs & git."""
    home = Path.home()
    extra_dirs = [
        '/opt/homebrew/bin',
        '/opt/homebrew/sbin',
        '/usr/local/bin',
        str(home / '.local' / 'bin'),
        str(home / '.npm-global' / 'bin'),
        str(home / '.volta' / 'bin'),
        str(home / '.cargo' / 'bin'),
    ]
    # Also include active nvm node bin if present
    nvm_versions = home / '.nvm' / 'versions' / 'node'
    if nvm_versions.is_dir():
        for vdir in sorted(nvm_versions.iterdir(), reverse=True):
            b = vdir / 'bin'
            if b.is_dir():
                extra_dirs.append(str(b))
                break

    current = os.environ.get('PATH', '')
    parts = [p for p in current.split(os.pathsep) if p]
    seen = set(parts)
    for d in extra_dirs:
        if d not in seen and os.path.isdir(d):
            parts.append(d)
            seen.add(d)
    os.environ['PATH'] = os.pathsep.join(parts)


def find_available_port(preferred: int = 8501, host: str = '127.0.0.1') -> int:
    for candidate in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, candidate))
                return int(s.getsockname()[1])
            except OSError:
                continue
    return preferred


def _wait_for_server(url: str, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f'{url}/api/about', timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.2)
    return False


def _open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    system = platform.system()
    if system == 'Darwin':
        subprocess.Popen(['open', str(path)])
    elif system == 'Windows':
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(['xdg-open', str(path)])


def _run_tk_control_window(url: str, workspace_dir: Path, stop_callback) -> bool:
    """Show a tiny native desktop control window so double-click users can reopen or quit cleanly."""
    try:
        import tkinter as tk
    except Exception:
        return False

    try:
        root = tk.Tk()
    except Exception:
        return False

    root.title(f'{APP_NAME} v{APP_VERSION}')
    root.geometry('410x235')
    root.resizable(False, False)
    root.configure(bg='#0f172a')

    # Header with Si badge
    top = tk.Frame(root, bg='#0f172a')
    top.pack(fill='x', padx=20, pady=(18, 10))

    badge = tk.Label(
        top,
        text='Si',
        bg='#EB0A1E',
        fg='#ffffff',
        font=('Helvetica', 16, 'bold'),
        width=3,
        height=1,
        padx=4,
        pady=4,
    )
    badge.pack(side='left')

    title_box = tk.Frame(top, bg='#0f172a')
    title_box.pack(side='left', padx=12)
    tk.Label(
        title_box,
        text=f'{APP_NAME}  v{APP_VERSION}',
        bg='#0f172a',
        fg='#f8fafc',
        font=('Helvetica', 14, 'bold'),
        anchor='w',
    ).pack(anchor='w')
    tk.Label(
        title_box,
        text=f'{APP_STAGE} Release · Local Architecture & Spec Studio',
        bg='#0f172a',
        fg='#94a3b8',
        font=('Helvetica', 10),
        anchor='w',
    ).pack(anchor='w')

    # Status info
    info = tk.Frame(root, bg='#1e293b', padx=12, pady=10)
    info.pack(fill='x', padx=20, pady=6)
    tk.Label(
        info,
        text=f'Running locally at:  {url}',
        bg='#1e293b',
        fg='#86efac',
        font=('Courier', 10, 'bold'),
        anchor='w',
    ).pack(fill='x')
    tk.Label(
        info,
        text=f'Workspace:  {workspace_dir}',
        bg='#1e293b',
        fg='#cbd5e1',
        font=('Helvetica', 9),
        anchor='w',
        wraplength=345,
        justify='left',
    ).pack(fill='x', pady=(4, 0))

    # Action buttons
    btns = tk.Frame(root, bg='#0f172a')
    btns.pack(fill='x', padx=20, pady=(14, 16))

    def on_open():
        webbrowser.open(url)

    def on_folder():
        _open_folder(workspace_dir)

    def on_quit():
        stop_callback()
        try:
            root.destroy()
        except Exception:
            pass

    tk.Button(
        btns,
        text='Open SPECiT in Browser',
        command=on_open,
        bg='#EB0A1E',
        fg='#ffffff',
        activebackground='#C50819',
        activeforeground='#ffffff',
        relief='flat',
        padx=12,
        pady=7,
        font=('Helvetica', 10, 'bold'),
        cursor='hand2',
    ).pack(side='left')

    tk.Button(
        btns,
        text='Workspace',
        command=on_folder,
        bg='#334155',
        fg='#f8fafc',
        activebackground='#475569',
        activeforeground='#ffffff',
        relief='flat',
        padx=10,
        pady=7,
        font=('Helvetica', 10),
        cursor='hand2',
    ).pack(side='left', padx=8)

    tk.Button(
        btns,
        text='Quit',
        command=on_quit,
        bg='#1e293b',
        fg='#fca5a5',
        activebackground='#7f1d1d',
        activeforeground='#ffffff',
        relief='flat',
        padx=10,
        pady=7,
        font=('Helvetica', 10),
        cursor='hand2',
    ).pack(side='right')

    root.protocol('WM_DELETE_WINDOW', on_quit)
    root.mainloop()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=f'{APP_NAME} v{APP_VERSION} ({APP_STAGE}) Desktop Launcher')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=int(os.environ.get('SPECIT_PORT', '8501')))
    parser.add_argument('--no-browser', action='store_true', help='Do not auto-open the web browser')
    parser.add_argument('--no-gui', action='store_true', help='Run in terminal/headless mode without Tk status window')
    args = parser.parse_args()

    _augment_path_for_gui_app()

    # Import app AFTER PATH augmentation so detected AI CLIs are visible
    import uvicorn
    import app as specit_app

    port = find_available_port(args.port, args.host)
    url = f'http://{args.host}:{port}'
    workspace_dir = default_workspace_root()

    config = uvicorn.Config(
        specit_app.app,
        host=args.host,
        port=port,
        log_level='warning' if getattr(sys, 'frozen', False) else 'info',
    )
    server = uvicorn.Server(config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    if _wait_for_server(url) and not args.no_browser:
        webbrowser.open(url)

    def stop_server():
        server.should_exit = True

    used_gui = False
    if not args.no_gui:
        used_gui = _run_tk_control_window(url, workspace_dir, stop_server)

    if not used_gui:
        print(f'{APP_NAME} v{APP_VERSION} ({APP_STAGE}) running at {url}')
        print(f'Workspace: {workspace_dir}')
        print('Press Ctrl+C to stop.')
        try:
            while server_thread.is_alive():
                server_thread.join(timeout=0.5)
        except KeyboardInterrupt:
            stop_server()

    server_thread.join(timeout=3.0)


if __name__ == '__main__':
    main()
