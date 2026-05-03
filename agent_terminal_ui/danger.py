"""Command danger level detection.

Analyzes shell commands to classify their risk level (SAFE, UNKNOWN,
DANGEROUS, DESTRUCTIVE). Used by the permissions screen to display
appropriate visual warnings.

Concept: AU-018 (Tool Safety)
"""

from __future__ import annotations

import re
from enum import Enum


class DangerLevel(Enum):
    """Classification of command risk level."""

    SAFE = "safe"
    UNKNOWN = "unknown"
    DANGEROUS = "dangerous"
    DESTRUCTIVE = "destructive"


# Commands that are always safe (read-only)
SAFE_COMMANDS = frozenset(
    {
        "cat",
        "head",
        "tail",
        "less",
        "more",
        "wc",
        "file",
        "stat",
        "du",
        "df",
        "ls",
        "dir",
        "find",
        "grep",
        "rg",
        "ag",
        "ack",
        "which",
        "whereis",
        "type",
        "echo",
        "printf",
        "date",
        "uptime",
        "whoami",
        "hostname",
        "uname",
        "env",
        "printenv",
        "pwd",
        "id",
        "groups",
        "ps",
        "top",
        "htop",
        "free",
        "lsof",
        "ss",
        "netstat",
        "ifconfig",
        "ip",
        "dig",
        "nslookup",
        "host",
        "ping",
        "traceroute",
        "curl",
        "wget",
        "python3",
        "python",
        "node",
        "git",
        "man",
        "help",
        "true",
        "false",
        "test",
        "basename",
        "dirname",
        "realpath",
        "readlink",
        "sha256sum",
        "md5sum",
        "diff",
        "sort",
        "uniq",
        "cut",
        "tr",
        "sed",
        "awk",
        "jq",
        "yq",
        "ruff",
        "mypy",
        "black",
        "isort",
        "pytest",
        "pre-commit",
    }
)

# Commands that could cause data loss
DESTRUCTIVE_COMMANDS = frozenset(
    {
        "rm",
        "rmdir",
        "shred",
        "dd",
        "mkfs",
        "fdisk",
        "parted",
        "format",
        "wipefs",
    }
)

# Commands that modify system state
DANGEROUS_COMMANDS = frozenset(
    {
        "mv",
        "cp",
        "chmod",
        "chown",
        "chgrp",
        "ln",
        "mount",
        "umount",
        "kill",
        "killall",
        "pkill",
        "shutdown",
        "reboot",
        "halt",
        "systemctl",
        "service",
        "iptables",
        "ufw",
        "firewall-cmd",
        "useradd",
        "userdel",
        "usermod",
        "groupadd",
        "groupdel",
        "passwd",
        "visudo",
        "crontab",
        "apt",
        "apt-get",
        "dpkg",
        "yum",
        "dnf",
        "pacman",
        "snap",
        "pip",
        "pip3",
        "npm",
        "yarn",
        "pnpm",
        "gem",
        "cargo",
        "docker",
        "podman",
        "kubectl",
    }
)

# Dangerous patterns in arguments
DANGEROUS_PATTERNS = [
    re.compile(r"\brm\s+-rf?\s+/"),  # rm -rf /
    re.compile(r"\brm\s+-rf?\s+~"),  # rm -rf ~
    re.compile(r"\brm\s+-rf?\s+\$HOME"),  # rm -rf $HOME
    re.compile(r"\bdd\s+.*of=/dev/"),  # dd of=/dev/*
    re.compile(r">\s*/dev/sd[a-z]"),  # redirect to disk
    re.compile(r"\bchmod\s+777"),  # chmod 777
    re.compile(r"\bchmod\s+-R\s+777"),  # chmod -R 777
    re.compile(r"\|.*\bsudo\b"),  # piping to sudo
    re.compile(r"\bcurl\s+.*\|\s*(?:ba)?sh"),  # curl | sh
    re.compile(r"\bwget\s+.*\|\s*(?:ba)?sh"),  # wget | sh
    re.compile(r"\bsudo\s+rm\b"),  # sudo rm
    re.compile(r":>\s+\S+"),  # truncate file with :>
]

# Destructive patterns
DESTRUCTIVE_PATTERNS = [
    re.compile(r"\brm\s+-rf?\s+/\s*$"),  # rm -rf /
    re.compile(r"\brm\s+-rf?\s+/\*"),  # rm -rf /*
    re.compile(r"\bdd\s+.*of=/dev/[sh]d[a-z]\b"),  # dd to disk
    re.compile(r"\bmkfs\b"),  # format filesystem
    re.compile(r">\s*/etc/passwd"),  # overwrite passwd
    re.compile(r">\s*/etc/shadow"),  # overwrite shadow
]


def classify_command(command: str) -> DangerLevel:
    """Classify the danger level of a shell command.

    Args:
        command: The shell command string to analyze.

    Returns:
        The DangerLevel classification.
    """
    command = command.strip()
    if not command:
        return DangerLevel.SAFE

    # Check destructive patterns first
    for pattern in DESTRUCTIVE_PATTERNS:
        if pattern.search(command):
            return DangerLevel.DESTRUCTIVE

    # Check dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if pattern.search(command):
            return DangerLevel.DANGEROUS

    # Check if sudo is used
    if command.startswith("sudo "):
        inner = command[5:].strip()
        inner_level = classify_command(inner)
        if inner_level == DangerLevel.SAFE:
            return DangerLevel.DANGEROUS
        return inner_level

    # Extract the base command
    base_cmd = _extract_base_command(command)

    if base_cmd in DESTRUCTIVE_COMMANDS:
        return DangerLevel.DESTRUCTIVE

    if base_cmd in DANGEROUS_COMMANDS:
        return DangerLevel.DANGEROUS

    if base_cmd in SAFE_COMMANDS:
        return DangerLevel.SAFE

    return DangerLevel.UNKNOWN


def get_danger_markup(level: DangerLevel) -> str:
    """Get Rich markup styling for a danger level.

    Args:
        level: The danger classification.

    Returns:
        Rich markup string for the level indicator.
    """
    if level == DangerLevel.SAFE:
        return "[$success]● SAFE[/$success]"
    elif level == DangerLevel.UNKNOWN:
        return "[$text-muted]● UNKNOWN[/$text-muted]"
    elif level == DangerLevel.DANGEROUS:
        return "[$warning]● DANGEROUS[/$warning]"
    elif level == DangerLevel.DESTRUCTIVE:
        return "[$error]● DESTRUCTIVE[/$error]"
    return ""


def _extract_base_command(command: str) -> str:
    """Extract the base command from a full command string.

    Handles pipes, redirections, and common prefixes.

    Args:
        command: The full command string.

    Returns:
        The base command name.
    """
    # Remove environment variable assignments
    cmd = re.sub(r"^\s*\w+=\S*\s+", "", command)

    # Remove leading path
    cmd = cmd.strip()

    # Handle pipes — use the first command
    if "|" in cmd:
        cmd = cmd.split("|")[0].strip()

    # Handle command substitution $()
    cmd = re.sub(r"\$\([^)]+\)", "", cmd)

    # Handle redirections
    cmd = re.sub(r"[<>].*", "", cmd).strip()

    # Handle semicolons — use first command
    if ";" in cmd:
        cmd = cmd.split(";")[0].strip()

    # Handle && — use first command
    if "&&" in cmd:
        cmd = cmd.split("&&")[0].strip()

    # Get the actual command name
    parts = cmd.split()
    if not parts:
        return ""

    # Get basename
    base = parts[0].split("/")[-1]
    return base
