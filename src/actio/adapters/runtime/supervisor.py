"""Windows ownership/containment; no upstream process internals."""
import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time

from actio.contracts.json import ContractError
from actio.adapters.filesystem.common import Lines
from actio.adapters.filesystem.common import clean_env
from actio.adapters.filesystem.common import uid
from actio.adapters.filesystem.common import write_json


class IO(C.Structure):
    _fields_ = [(n, C.c_ulonglong) for n in ('readOps','writeOps','otherOps','readBytes','writeBytes','otherBytes')]


class Basic(C.Structure):
    _fields_ = [('processTime',C.c_longlong),('jobTime',C.c_longlong),('flags',W.DWORD),
                ('minWS',C.c_size_t),('maxWS',C.c_size_t),('activeLimit',W.DWORD),
                ('affinity',C.c_size_t),('priority',W.DWORD),('scheduling',W.DWORD)]


class Extended(C.Structure):
    _fields_ = [('basic',Basic),('io',IO),('processMemory',C.c_size_t),('jobMemory',C.c_size_t),
                ('peakProcess',C.c_size_t),('peakJob',C.c_size_t)]


class Accounting(C.Structure):
    _fields_ = [(n,C.c_longlong) for n in ('user','kernel','periodUser','periodKernel')] + [
        (n,W.DWORD) for n in ('pageFaults','totalProcesses','activeProcesses','terminatedProcesses')]


def kernel():
    if sys.platform != 'win32':
        raise ContractError('validated supervisor requires Windows x64')
    k = C.WinDLL('kernel32', use_last_error=True)
    signatures = {
        'CreateJobObjectW': ([C.c_void_p,W.LPCWSTR],W.HANDLE),
        'OpenJobObjectW': ([W.DWORD,W.BOOL,W.LPCWSTR],W.HANDLE),
        'SetInformationJobObject': ([W.HANDLE,C.c_int,C.c_void_p,W.DWORD],W.BOOL),
        'AssignProcessToJobObject': ([W.HANDLE,W.HANDLE],W.BOOL),
        'QueryInformationJobObject': ([W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.c_void_p],W.BOOL),
        'TerminateJobObject': ([W.HANDLE,W.UINT],W.BOOL),
        'CloseHandle': ([W.HANDLE],W.BOOL),
        'OpenProcess': ([W.DWORD,W.BOOL,W.DWORD],W.HANDLE),
        'GetProcessTimes': ([W.HANDLE,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p],W.BOOL),
        'GetExitCodeProcess': ([W.HANDLE,C.c_void_p],W.BOOL),
    }
    for name, (args, result) in signatures.items():
        getattr(k,name).argtypes = args
        getattr(k,name).restype = result
    return k


def process_birth(pid):
    k = kernel()
    handle = k.OpenProcess(0x1000, False, pid)
    if not handle:
        error = C.get_last_error()
        if error == 87:
            return None
        raise C.WinError(error)
    try:
        code = W.DWORD()
        if not k.GetExitCodeProcess(handle, C.byref(code)):
            raise C.WinError(C.get_last_error())
        if code.value != 259:
            return None
        times = [C.c_ulonglong() for _ in range(4)]
        if not k.GetProcessTimes(handle, *(C.byref(t) for t in times)):
            raise C.WinError(C.get_last_error())
        return str(times[0].value)
    finally:
        k.CloseHandle(handle)


class Job:
    def __init__(self, process, name, memory=768*1024*1024):
        self.k = kernel()
        self.handle = self.k.CreateJobObjectW(None, name)  # Non-inheritable SECURITY_ATTRIBUTES=NULL.
        if not self.handle:
            raise C.WinError(C.get_last_error())
        try:
            if C.get_last_error() == 183:
                raise ContractError('job name collision')
            limits = Extended()
            limits.basic.flags = 0x2000 | 0x100 | 0x200 | 0x8
            limits.basic.activeLimit = 12
            limits.processMemory = memory
            limits.jobMemory = memory * 2
            if not self.k.SetInformationJobObject(self.handle,9,C.byref(limits),C.sizeof(limits)):
                raise C.WinError(C.get_last_error())
            # _handle belongs to our Popen, never the third-party SDK.
            if not self.k.AssignProcessToJobObject(self.handle,W.HANDLE(int(process._handle))):
                raise C.WinError(C.get_last_error())
        except BaseException:
            self.k.CloseHandle(self.handle)
            self.handle = None
            raise

    def snapshot(self):
        a = Accounting()
        if not self.k.QueryInformationJobObject(self.handle,1,C.byref(a),C.sizeof(a),None):
            raise C.WinError(C.get_last_error())
        return {'total': a.totalProcesses, 'active': a.activeProcesses, 'terminated': a.terminatedProcesses}

    def close(self):
        before = self.snapshot()
        if before['active'] and not self.k.TerminateJobObject(self.handle,90):
            raise C.WinError(C.get_last_error())
        deadline = time.monotonic() + 5
        while (after := self.snapshot())['active'] and time.monotonic() < deadline:
            time.sleep(.01)
        self.k.CloseHandle(self.handle)
        self.handle = None
        if after['active']:
            raise ContractError('job cleanup unconfirmed')
        return {'before': before, 'after': after}


def reap_named_job(name):
    k = kernel()
    handle = k.OpenJobObjectW(0x8 | 0x4, False, name)  # TERMINATE | QUERY
    if not handle:
        if C.get_last_error() == 2:
            return {'absent': True, 'active': 0}
        raise C.WinError(C.get_last_error())
    job = object.__new__(Job)
    job.k, job.handle = k, handle
    return job.close()


def owned_root(parent, owner):
    parent = Path(parent).absolute()
    for p in (parent, *parent.parents):
        if p.exists() and (p.is_symlink() or p.is_junction()):
            raise ContractError('short root must not traverse reparse points')
    parent.mkdir(parents=True, exist_ok=True)
    root = parent / ('w' + uid()[:12])
    if len(str(root)) > 80:
        raise ContractError('use a shorter isolated root; configure paths.runs in actio.toml')
    root.mkdir()
    if root.resolve() != root:
        raise ContractError('short root resolution changed')
    if shutil.disk_usage(root).free < 256*1024*1024:
        raise ContractError('short root requires at least 256 MiB free disk')
    write_json(root/'owner.json', {'owner': owner, 'root': str(root), 'version': 1})
    return root


class Supervisor:
    """Owned child waits on stdin until Job assignment succeeds. No daemon threads."""
    def __init__(self, root, job_name, *, module='actio.interfaces.workers.host', limits=None):
        self.root, self.job_name, self.module = Path(root), job_name, module
        self.limits = {'item': 65536, 'total': 8*1024*1024, 'count': 4096, 'disk': 128*1024*1024,
                       'memory': 768*1024*1024, **(limits or {})}
        self.reader = Lines(self.root/'host.jsonl', **{k:self.limits[k] for k in ('item','total','count')})
        self.proc = self.job = None
        self.log = None
        self.execution_deadline = None

    def start(self):
        self.execution_deadline = time.monotonic()+getattr(self,'total_seconds',75)
        self.log = (self.root/'stderr.log').open('wb')
        self.proc = subprocess.Popen([sys.executable,'-m',self.module,str(self.root)],
            stdin=subprocess.PIPE, stdout=self.log, stderr=self.log, cwd=self.root,
            env=clean_env(self.root), close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.job = Job(self.proc, self.job_name, self.limits['memory'])
        except BaseException:
            self.proc.kill()
            self.proc.wait(timeout=5)
            self.log.close()
            raise
        credential=getattr(self,'launch_credential',None)
        try:self.send({'kind':'go',**({'credential':credential} if credential else {})})
        finally:self.launch_credential=None

    def send(self, value):
        from actio.contracts.json import canonical
        data = (canonical(value)+'\n').encode()
        if len(data) > self.limits['item']:
            raise ContractError('command limit')
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def check_disk(self):
        if any(self.root.glob('*.limit')):
            raise ContractError('data_limit_exceeded; prefix retained')
        total = count = 0
        for parent, dirs, files in os.walk(self.root, followlinks=False):
            for name in dirs + files:
                path = Path(parent)/name
                if path.is_symlink() or path.is_junction():
                    raise ContractError('unexpected reparse point in task root')
            for name in files:
                try:
                    size = (Path(parent)/name).stat().st_size
                except FileNotFoundError:
                    # DSH atomically replaces session files while the Worker runs.
                    # Vanished entries consume no current disk; other I/O errors propagate.
                    continue
                count += 1
                total += size
                if total > self.limits['disk'] or count > 2048:
                    raise ContractError('disk_limit_exceeded')

    def wait(self, kind, seconds, on_record=lambda r: None):
        deadline = min(time.monotonic() + seconds,self.execution_deadline)
        while time.monotonic() < deadline:
            self.check_disk()
            found = None
            for record in self.reader.poll():
                on_record(record)
                if record['kind'] == 'error':
                    raise ContractError('SDK host: ' + record['error'])
                if record['kind'] == kind:
                    found = record
            if found is not None:
                return found
            if self.proc.poll() is not None:
                raise ContractError('SDK host exited before ' + kind)
            time.sleep(.015)
        raise TimeoutError(kind + ' deadline')

    def close(self):
        report = self.job.close() if self.job and self.job.handle else {'not_assigned': True, 'active': 0}
        if self.proc:
            self.proc.wait(timeout=5)
            if self.proc.stdin:
                self.proc.stdin.close()
        if self.log:
            self.log.close()
        return report
