"""PTY shell integration for the terminal UI.

Provides a persistent shell session with full PTY support,
enabling command execution, ANSI rendering, and tab completion.
Modeled after Toad's shell architecture.

Concept: AU-018 (Shell Integration)
"""

from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import pty
import select
import signal
import struct
import sys
import termios

from textual.message import Message

logger = logging.getLogger(__name__)


class Shell:
    """A persistent PTY shell session.

    Manages a pseudo-terminal (PTY) for running shell commands with
    full terminal emulation support. Enables interactive shell sessions
    within the Agent Terminal UI.
    """

    class OutputReceived(Message):
        """Posted when output is received from the shell."""

        def __init__(self, data: str) -> None:
            self.data = data
            super().__init__()

    class ProcessExited(Message):
        """Posted when a shell process exits."""

        def __init__(self, returncode: int) -> None:
            self.returncode = returncode
            super().__init__()

    class CurrentWorkingDirectoryChanged(Message):
        """Posted when the shell's working directory changes."""

        def __init__(self, path: str) -> None:
            self.path = path
            super().__init__()

    def __init__(
        self,
        shell_path: str | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """Initialize the shell.

        Args:
            shell_path: Path to the shell executable (default: $SHELL or /bin/bash).
            cwd: Working directory for the shell.
            env: Additional environment variables.
        """
        self._shell_path = shell_path or os.environ.get("SHELL", "/bin/bash")
        self._cwd = cwd or os.getcwd()
        self._env = {**os.environ}
        if env:
            self._env.update(env)

        self._master_fd: int | None = None
        self._slave_fd: int | None = None
        self._pid: int | None = None
        self._running = False
        self._output_buffer: list[str] = []

    @property
    def running(self) -> bool:
        """Whether the shell process is currently active."""
        return self._running

    @property
    def cwd(self) -> str:
        """The current working directory of the shell."""
        return self._cwd

    @property
    def pid(self) -> int | None:
        """The PID of the shell process."""
        return self._pid

    def start(self) -> None:
        """Start the shell process with a PTY."""
        if self._running:
            return

        # Create pseudo-terminal
        self._master_fd, self._slave_fd = pty.openpty()

        # Set terminal size
        self._set_terminal_size(80, 24)

        # Fork process
        self._pid = os.fork()

        if self._pid == 0:
            # Child process
            os.close(self._master_fd)

            # Create new session
            os.setsid()

            # Set controlling terminal
            fcntl.ioctl(self._slave_fd, termios.TIOCSCTTY, 0)

            # Redirect stdio to PTY
            os.dup2(self._slave_fd, 0)
            os.dup2(self._slave_fd, 1)
            os.dup2(self._slave_fd, 2)

            if self._slave_fd > 2:
                os.close(self._slave_fd)

            # Change directory
            os.chdir(self._cwd)

            # Set environment
            self._env["TERM"] = "xterm-256color"
            self._env["COLUMNS"] = "80"
            self._env["LINES"] = "24"

            # Execute shell
            os.execvpe(  # nosec B606
                self._shell_path,
                [self._shell_path, "--login"],
                self._env,
            )
            # Should not reach here
            sys.exit(1)
        else:
            # Parent process
            os.close(self._slave_fd)
            self._slave_fd = None
            self._running = True

            # Set non-blocking mode
            flags = fcntl.fcntl(self._master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self._master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def stop(self) -> None:
        """Stop the shell process."""
        if not self._running:
            return

        if self._pid:
            try:
                os.kill(self._pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

        if self._master_fd is not None:
            os.close(self._master_fd)
            self._master_fd = None

        self._running = False
        self._pid = None

    def write(self, data: str) -> None:
        """Write data to the shell's stdin.

        Args:
            data: The string to send to the shell.
        """
        if self._master_fd is not None and self._running:
            os.write(self._master_fd, data.encode())

    def read(self, timeout: float = 0.1) -> str | None:
        """Read available output from the shell.

        Args:
            timeout: Maximum time to wait for output in seconds.

        Returns:
            The output string, or None if no output is available.
        """
        if self._master_fd is None or not self._running:
            return None

        try:
            ready, _, _ = select.select([self._master_fd], [], [], timeout)
            if ready:
                data = os.read(self._master_fd, 4096)
                if data:
                    return data.decode("utf-8", errors="replace")
        except (OSError, ValueError):
            self._running = False

        return None

    async def read_async(self, timeout: float = 0.1) -> str | None:
        """Async version of read.

        Args:
            timeout: Maximum time to wait for output.

        Returns:
            The output string, or None.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.read, timeout)

    def resize(self, cols: int, rows: int) -> None:
        """Resize the PTY terminal.

        Args:
            cols: Number of columns.
            rows: Number of rows.
        """
        self._set_terminal_size(cols, rows)

    def _set_terminal_size(self, cols: int, rows: int) -> None:
        """Set the terminal window size.

        Args:
            cols: Number of columns.
            rows: Number of rows.
        """
        fd = self._master_fd or self._slave_fd
        if fd is not None:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

    def send_signal(self, sig: int) -> None:
        """Send a signal to the shell process.

        Args:
            sig: The signal number to send.
        """
        if self._pid:
            try:
                os.kill(self._pid, sig)
            except ProcessLookupError:
                self._running = False

    def send_interrupt(self) -> None:
        """Send Ctrl+C (SIGINT) to the shell."""
        self.write("\x03")

    def send_eof(self) -> None:
        """Send Ctrl+D (EOF) to the shell."""
        self.write("\x04")

    async def run_command(self, command: str) -> str:
        """Execute a command and return its output.

        This is a convenience method for running a single command
        and collecting its output. For interactive use, use
        write() and read() directly.

        Args:
            command: The shell command to execute.

        Returns:
            The collected output from the command.
        """
        if not self._running:
            self.start()

        self.write(command + "\n")

        output_parts: list[str] = []
        empty_reads = 0

        while empty_reads < 10:
            data = await self.read_async(timeout=0.1)
            if data:
                output_parts.append(data)
                empty_reads = 0
            else:
                empty_reads += 1

        return "".join(output_parts)

    def __del__(self) -> None:
        """Cleanup on garbage collection."""
        self.stop()


class ShellManager:
    """Manages multiple shell sessions.

    Provides session lifecycle management for concurrent shell instances,
    supporting the multi-session architecture.
    """

    def __init__(self) -> None:
        """Initialize the shell manager."""
        self._shells: dict[str, Shell] = {}
        self._active_shell_id: str | None = None

    @property
    def active_shell(self) -> Shell | None:
        """The currently active shell session."""
        if self._active_shell_id:
            return self._shells.get(self._active_shell_id)
        return None

    def create_shell(
        self,
        session_id: str,
        *,
        shell_path: str | None = None,
        cwd: str | None = None,
    ) -> Shell:
        """Create a new shell session.

        Args:
            session_id: Unique identifier for the session.
            shell_path: Path to the shell executable.
            cwd: Working directory.

        Returns:
            The created Shell instance.
        """
        shell = Shell(shell_path=shell_path, cwd=cwd)
        self._shells[session_id] = shell
        if self._active_shell_id is None:
            self._active_shell_id = session_id
        return shell

    def get_shell(self, session_id: str) -> Shell | None:
        """Get a shell by session ID.

        Args:
            session_id: The session identifier.

        Returns:
            The Shell instance or None.
        """
        return self._shells.get(session_id)

    def set_active(self, session_id: str) -> None:
        """Set the active shell session.

        Args:
            session_id: The session to make active.
        """
        if session_id in self._shells:
            self._active_shell_id = session_id

    def close_shell(self, session_id: str) -> None:
        """Close and remove a shell session.

        Args:
            session_id: The session to close.
        """
        shell = self._shells.pop(session_id, None)
        if shell:
            shell.stop()
        if self._active_shell_id == session_id:
            self._active_shell_id = next(iter(self._shells)) if self._shells else None

    def close_all(self) -> None:
        """Close all shell sessions."""
        for shell in self._shells.values():
            shell.stop()
        self._shells.clear()
        self._active_shell_id = None


class JobRecord:
    """Tracks a shell job with metadata.

    Concept: TUI-12 (Job Center)
    """

    def __init__(
        self,
        job_id: str,
        command: str,
        cwd: str = "",
        shell_session_id: str = "",
        task_id: str = "",
    ) -> None:
        """Initialize a job record.

        Args:
            job_id: Unique job identifier.
            command: The shell command.
            cwd: Working directory.
            shell_session_id: Associated shell session.
            task_id: Linked task ID (optional).
        """
        self.job_id = job_id
        self.command = command
        self.cwd = cwd
        self.shell_session_id = shell_session_id
        self.task_id = task_id
        self.status = "running"  # running | completed | failed | cancelled
        self.exit_code: int | None = None
        self.started_at = __import__("time").time()
        self.completed_at: float | None = None
        self.output_tail: list[str] = []
        self._max_tail_lines = 50

    @property
    def elapsed_ms(self) -> int:
        """Elapsed time in milliseconds."""
        end = self.completed_at or __import__("time").time()
        return int((end - self.started_at) * 1000)

    @property
    def elapsed_display(self) -> str:
        """Human-readable elapsed time."""
        ms = self.elapsed_ms
        if ms < 1000:
            return f"{ms}ms"
        secs = ms / 1000
        if secs < 60:
            return f"{secs:.1f}s"
        mins = secs / 60
        return f"{mins:.1f}m"

    def append_output(self, line: str) -> None:
        """Append a line to the output tail buffer.

        Args:
            line: Output line to record.
        """
        self.output_tail.append(line)
        if len(self.output_tail) > self._max_tail_lines:
            self.output_tail = self.output_tail[-self._max_tail_lines :]

    def complete(self, exit_code: int) -> None:
        """Mark the job as completed.

        Args:
            exit_code: The process exit code.
        """
        import time as _time

        self.exit_code = exit_code
        self.completed_at = _time.time()
        self.status = "completed" if exit_code == 0 else "failed"

    def cancel(self) -> None:
        """Mark the job as cancelled."""
        import time as _time

        self.completed_at = _time.time()
        self.status = "cancelled"

    def to_dict(self) -> dict:
        """Serialize to a dictionary."""
        return {
            "job_id": self.job_id,
            "command": self.command,
            "cwd": self.cwd,
            "status": self.status,
            "exit_code": self.exit_code,
            "elapsed_ms": self.elapsed_ms,
            "elapsed_display": self.elapsed_display,
            "task_id": self.task_id,
            "output_tail_lines": len(self.output_tail),
        }


class JobCenter:
    """Manages shell job tracking and lifecycle.

    Provides a registry of running and completed shell jobs with
    output tailing, status queries, and linked task references.
    """

    def __init__(self) -> None:
        """Initialize the job center."""
        self._jobs: dict[str, JobRecord] = {}
        self._next_id = 1

    @property
    def jobs(self) -> dict[str, JobRecord]:
        """All tracked jobs."""
        return self._jobs

    def create_job(
        self,
        command: str,
        cwd: str = "",
        shell_session_id: str = "",
        task_id: str = "",
    ) -> JobRecord:
        """Create and register a new job.

        Args:
            command: The shell command.
            cwd: Working directory.
            shell_session_id: Associated shell session.
            task_id: Linked task ID.

        Returns:
            The created job record.
        """
        job_id = str(self._next_id)
        self._next_id += 1
        job = JobRecord(
            job_id=job_id,
            command=command,
            cwd=cwd,
            shell_session_id=shell_session_id,
            task_id=task_id,
        )
        self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> JobRecord | None:
        """Get a job by ID.

        Args:
            job_id: The job identifier.

        Returns:
            The job record or None.
        """
        return self._jobs.get(job_id)

    def list_jobs(self, status: str | None = None) -> list[JobRecord]:
        """List jobs, optionally filtered by status.

        Args:
            status: Optional status filter.

        Returns:
            List of matching job records.
        """
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        return sorted(jobs, key=lambda j: j.started_at, reverse=True)

    def cancel_job(
        self, job_id: str, shell_manager: ShellManager | None = None
    ) -> bool:
        """Cancel a running job.

        Args:
            job_id: The job to cancel.
            shell_manager: Optional shell manager to send SIGINT.

        Returns:
            True if the job was cancelled.
        """
        job = self._jobs.get(job_id)
        if job is None or job.status != "running":
            return False

        if shell_manager and job.shell_session_id:
            shell = shell_manager.get_shell(job.shell_session_id)
            if shell:
                shell.send_interrupt()

        job.cancel()
        return True

    def get_output(self, job_id: str, lines: int = 20) -> list[str]:
        """Get the tail output of a job.

        Args:
            job_id: The job identifier.
            lines: Number of tail lines to return.

        Returns:
            List of output lines.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return []
        return job.output_tail[-lines:]

    def cleanup_completed(self, max_keep: int = 50) -> int:
        """Remove old completed jobs beyond max_keep.

        Args:
            max_keep: Maximum completed jobs to retain.

        Returns:
            Number of jobs cleaned up.
        """
        completed = [j for j in self._jobs.values() if j.status != "running"]
        completed.sort(key=lambda j: j.started_at)

        removed = 0
        while len(completed) > max_keep:
            old = completed.pop(0)
            del self._jobs[old.job_id]
            removed += 1

        return removed

    def summary(self) -> dict:
        """Get a summary of all jobs."""
        running = sum(1 for j in self._jobs.values() if j.status == "running")
        completed = sum(1 for j in self._jobs.values() if j.status == "completed")
        failed = sum(1 for j in self._jobs.values() if j.status == "failed")
        cancelled = sum(1 for j in self._jobs.values() if j.status == "cancelled")
        return {
            "total": len(self._jobs),
            "running": running,
            "completed": completed,
            "failed": failed,
            "cancelled": cancelled,
        }
