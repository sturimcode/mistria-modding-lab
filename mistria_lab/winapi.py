"""Windows process helpers: start the game on a hidden desktop or off-screen, and find it by folder."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import time
from pathlib import Path

DESKTOP_NAME = 'MistriaModdingLab'
GENERIC_ALL = 0x10000000
STILL_ACTIVE = 259


class StartupInfo(ctypes.Structure):
    _fields_ = [('cb', wt.DWORD), ('lpReserved', wt.LPWSTR), ('lpDesktop', wt.LPWSTR), ('lpTitle', wt.LPWSTR),
                ('dwX', wt.DWORD), ('dwY', wt.DWORD), ('dwXSize', wt.DWORD), ('dwYSize', wt.DWORD),
                ('dwXCountChars', wt.DWORD), ('dwYCountChars', wt.DWORD), ('dwFillAttribute', wt.DWORD),
                ('dwFlags', wt.DWORD), ('wShowWindow', wt.WORD), ('cbReserved2', wt.WORD),
                ('lpReserved2', ctypes.c_void_p), ('hStdInput', wt.HANDLE), ('hStdOutput', wt.HANDLE),
                ('hStdError', wt.HANDLE)]


class ProcessInfo(ctypes.Structure):
    _fields_ = [('hProcess', wt.HANDLE), ('hThread', wt.HANDLE), ('dwProcessId', wt.DWORD), ('dwThreadId', wt.DWORD)]


def start_hidden(exe: Path, args: list[str], cwd: Path, env: dict) -> int:
    """Start a process on a separate desktop. It renders there and never shows on screen or takes keyboard focus.

    Windows removes the desktop after the last process on it closes.
    """
    k, u = ctypes.windll.kernel32, ctypes.windll.user32
    k.CreateProcessW.argtypes = [wt.LPCWSTR, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wt.BOOL, wt.DWORD,
                                 ctypes.c_void_p, wt.LPCWSTR, ctypes.POINTER(StartupInfo), ctypes.POINTER(ProcessInfo)]
    k.CloseHandle.argtypes = [wt.HANDLE]
    u.CreateDesktopW.restype = wt.HANDLE
    u.CreateDesktopW.argtypes = [wt.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, wt.DWORD, wt.DWORD, ctypes.c_void_p]
    desktop = u.CreateDesktopW(DESKTOP_NAME, None, None, 0, GENERIC_ALL, None)
    if not desktop:
        raise OSError('could not create the hidden desktop')
    si = StartupInfo()
    si.cb = ctypes.sizeof(StartupInfo)
    si.lpDesktop = DESKTOP_NAME
    pi = ProcessInfo()
    saved = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    try:
        line = subprocess.list2cmdline([str(exe), *args])
        ok = k.CreateProcessW(str(exe), line, None, None, False, 0, None, str(cwd), ctypes.byref(si), ctypes.byref(pi))
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    if not ok:
        raise OSError(f'could not start {exe}: Windows error {ctypes.GetLastError()}')
    k.CloseHandle(pi.hThread)
    k.CloseHandle(pi.hProcess)
    return pi.dwProcessId


def start_visible(exe: Path, args: list[str], cwd: Path, env: dict) -> int:
    return subprocess.Popen([str(exe), *args], cwd=cwd, env=dict(os.environ, **env),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).pid


def move_offscreen(pid: int, timeout: float = 30) -> bool:
    """Move the game's main window off the visible desktop. It keeps rendering there."""
    u = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    u.EnumWindows.argtypes = [callback_type, wt.LPARAM]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found: list = []

        def visit(hwnd, _):
            owner = wt.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == pid and u.IsWindowVisible(hwnd):
                r = wt.RECT()
                u.GetWindowRect(hwnd, ctypes.byref(r))
                if r.right - r.left > 100:
                    found.append(hwnd)
            return True

        u.EnumWindows(callback_type(visit), 0)
        if found:
            # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
            u.SetWindowPos(found[0], 0, -5000, -5000, 0, 0, 0x0001 | 0x0004 | 0x0010)
            return True
        time.sleep(0.2)
    return False


def game_processes() -> list[tuple[int, str]]:
    """Every process whose name starts with FieldsOfMistria, as (pid, full path)."""
    script = ("Get-Process | Where-Object { $_.ProcessName -like 'FieldsOfMistria*' } | "
              "ForEach-Object { \"$($_.Id)|$($_.Path)\" }")
    out = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
                         capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines():
        if '|' in line:
            pid, path = line.strip().split('|', 1)
            rows.append((int(pid), path))
    return rows


def kill(pid: int) -> None:
    subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True)
