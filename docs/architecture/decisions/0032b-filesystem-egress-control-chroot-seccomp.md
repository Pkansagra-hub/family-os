# ADR-0032b: Filesystem Egress Control (chroot + seccomp)

**Status:** ✅ Approved
**Date:** 2025-10-13
**Parent ADR:** [ADR-0032: Band-Based Egress Rules](0032-band-based-egress-rules.md)
**Authors:** K1 Architecture Team
**Category:** Security & Privacy
**Related ADRs:** ADR-0032a (Network Egress), ADR-0033 (3-Tier Sandbox), ADR-0035 (PII Detection)

---

## Context

### Problem Statement

**Tools require filesystem access to read inputs, write outputs, and execute binaries, but unrestricted filesystem access enables data exfiltration, tampering, and privilege escalation.**

**Privacy Band Requirements:**
- **GREEN Band:** Read-only access to /tmp/session/, write to /tmp/output/
- **AMBER Band:** Read-only with PII masking, write to /tmp/output/
- **RED Band:** Minimal filesystem (read-only input, ephemeral output)
- **BLACK Band:** NO FILESYSTEM (complete isolation)

**Without Filesystem Egress Control:**
```
Malicious Scenario:
- Tool: "image_processor" (GREEN band)
- User: "Apply filter to photo.jpg"

Attack Execution:
1. Tool reads /home/user/.ssh/id_rsa ❌ (SSH keys)
2. Tool reads /etc/passwd ❌ (system files)
3. Tool writes /tmp/../../../etc/cron.d/backdoor ❌ (path traversal)
4. Tool opens("/dev/sda", O_WRONLY) ❌ (disk tampering)
5. Tool spawns shell via ptrace() ❌ (privilege escalation)

Impact: Credentials stolen, system compromised, data tampered
```

**With This Sub-ADR:**
```
Secure Execution:
- Tool: "image_processor" (GREEN band)
- chroot: /var/k1/jail/session_abc123/
- Allowed: /tmp/input/ (read-only), /tmp/output/ (write)

Execution:
1. Tool reads /tmp/input/photo.jpg ✅
2. Tool reads /home/user/.ssh/id_rsa ❌ (ENOENT - outside chroot)
3. Tool writes /tmp/output/filtered.jpg ✅
4. Tool writes /tmp/../../../etc/cron.d/backdoor ❌ (blocked by seccomp)
5. Tool ptrace() ❌ (blocked by seccomp)

Result: Image processed safely, all attacks blocked ✅
```

### System Constraints

1. **Performance Requirements:**
   - chroot setup: <3ms per tool launch
   - seccomp filter load: <1ms
   - Runtime overhead: 0ms (kernel-enforced)

2. **Security Requirements:**
   - 100% path traversal prevention
   - Dangerous syscalls blocked (mount, ptrace, reboot)
   - Read-only enforcement for system libraries
   - Ephemeral jail cleanup (<100ms)

3. **Compatibility:**
   - Linux: chroot + seccomp-bpf (kernel 3.5+)
   - Requires CAP_SYS_CHROOT and CAP_SYS_ADMIN

---

## Decision

### Filesystem Isolation Architecture

**2-Layer Filesystem Control:**
1. **chroot Jail** → Isolates root directory per tool
2. **seccomp-bpf Filter** → Blocks dangerous syscalls (mount, ptrace, etc.)

### Privacy Band Filesystem Policies

```yaml
# File: k1/config/filesystem_egress_policies.yml

filesystem_egress:
  # GREEN Band: Read-only inputs, writable outputs
  green_band:
    jail_template: "/var/k1/jails/green_template/"
    read_only_paths:
      - "/tmp/input/"          # Tool inputs
      - "/usr/lib/"            # System libraries
      - "/usr/bin/"            # Binaries
    writable_paths:
      - "/tmp/output/"         # Tool outputs only
    blocked_paths:
      - "/home/"
      - "/root/"
      - "/etc/shadow"
      - "/dev/"                # Block device access
    max_file_size: 100MB

  # AMBER Band: Same as GREEN + PII masking
  amber_band:
    jail_template: "/var/k1/jails/amber_template/"
    read_only_paths:
      - "/tmp/input/"          # PII-masked inputs
      - "/usr/lib/"
      - "/usr/bin/"
    writable_paths:
      - "/tmp/output/"
    blocked_paths:
      - "/home/"
      - "/root/"
      - "/etc/"
      - "/dev/"
    max_file_size: 100MB
    pii_masking: true

  # RED Band: Minimal ephemeral filesystem
  red_band:
    jail_template: "/var/k1/jails/red_template/"
    read_only_paths:
      - "/tmp/input/"          # Ephemeral input only
    writable_paths:
      - "/tmp/output/"         # Ephemeral output only
    blocked_paths:
      - "*"                    # Block everything else
    max_file_size: 10MB
    ephemeral: true            # Destroyed after tool exit

  # BLACK Band: No filesystem
  black_band:
    jail_template: null
    read_only_paths: []
    writable_paths: []
    blocked_paths: ["*"]
```

### chroot Jail Implementation

```python
# File: k1/security/filesystem_egress.py

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

@dataclass
class FilesystemPolicy:
    """Filesystem egress policy for tool"""
    tool_pid: int
    band: str
    jail_root: Path
    read_only_paths: List[str]
    writable_paths: List[str]
    blocked_paths: List[str]
    max_file_size: int  # bytes

class ChrootFilesystemController:
    """
    Control tool filesystem access via chroot jails
    Enforces privacy band policies with read-only mounts
    """

    def __init__(self, jail_base: Path = Path("/var/k1/jails")):
        self.jail_base = jail_base
        self.active_jails: Dict[int, Path] = {}  # pid → jail path
        self._ensure_jail_templates()

    def _ensure_jail_templates(self):
        """Create jail templates for each privacy band"""
        templates = {
            "green_template": [
                "tmp/input",
                "tmp/output",
                "usr/lib",
                "usr/bin",
                "lib",
                "lib64"
            ],
            "amber_template": [
                "tmp/input",
                "tmp/output",
                "usr/lib",
                "usr/bin",
                "lib",
                "lib64"
            ],
            "red_template": [
                "tmp/input",
                "tmp/output"
            ]
        }

        for template_name, dirs in templates.items():
            template_root = self.jail_base / template_name
            template_root.mkdir(parents=True, exist_ok=True)

            for dir_path in dirs:
                (template_root / dir_path).mkdir(parents=True, exist_ok=True)

            # Copy essential system libraries
            if "usr/lib" in dirs:
                self._copy_system_libs(template_root)

    def _copy_system_libs(self, jail_root: Path):
        """Copy essential system libraries to jail"""
        essential_libs = [
            "/lib/x86_64-linux-gnu/libc.so.6",
            "/lib/x86_64-linux-gnu/libpthread.so.0",
            "/lib/x86_64-linux-gnu/libdl.so.2",
            "/lib64/ld-linux-x86-64.so.2"
        ]

        for lib in essential_libs:
            if os.path.exists(lib):
                dest = jail_root / lib.lstrip("/")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(lib, dest)

    async def create_jail(self, policy: FilesystemPolicy) -> Path:
        """
        Create ephemeral chroot jail for tool (<3ms)
        Returns jail root path
        """
        if policy.band == "BLACK":
            # No filesystem
            return None

        # Create ephemeral jail from template
        template_name = f"{policy.band.lower()}_template"
        jail_id = f"session_{policy.tool_pid}"
        jail_root = self.jail_base / jail_id

        # Copy template
        template_root = self.jail_base / template_name
        shutil.copytree(template_root, jail_root, symlinks=True)

        # Mount read-only paths
        for ro_path in policy.read_only_paths:
            jail_path = jail_root / ro_path.lstrip("/")
            if jail_path.exists():
                # Bind mount as read-only
                subprocess.run([
                    "mount", "--bind", "-o", "ro",
                    str(jail_path), str(jail_path)
                ], check=True)

        self.active_jails[policy.tool_pid] = jail_root

        logger.info(
            f"Created chroot jail",
            pid=policy.tool_pid,
            band=policy.band,
            jail_root=str(jail_root)
        )

        return jail_root

    async def enter_jail(self, pid: int, jail_root: Path):
        """Enter chroot jail for process"""
        try:
            os.chroot(jail_root)
            os.chdir("/")
            logger.info(f"Process {pid} entered chroot jail: {jail_root}")
        except OSError as e:
            logger.error(f"Failed to enter jail: {e}")
            raise

    async def destroy_jail(self, pid: int):
        """
        Destroy ephemeral jail (<100ms)
        Unmounts and deletes jail directory
        """
        if pid not in self.active_jails:
            return

        jail_root = self.active_jails[pid]

        # Unmount all bind mounts
        mounts = subprocess.run(
            ["findmnt", "-R", "-n", "-o", "TARGET", str(jail_root)],
            capture_output=True,
            text=True
        ).stdout.strip().split("\n")

        for mount in reversed(mounts):
            if mount:
                subprocess.run(["umount", mount], stderr=subprocess.DEVNULL)

        # Delete jail
        shutil.rmtree(jail_root, ignore_errors=True)
        del self.active_jails[pid]

        logger.info(f"Destroyed jail: pid={pid}, jail={jail_root}")
```

### seccomp-bpf Syscall Filtering

```python
# File: k1/security/seccomp_filter.py

import ctypes
import ctypes.util
from enum import IntEnum

class SeccompAction(IntEnum):
    """seccomp-bpf actions"""
    ALLOW = 0x7fff0000
    KILL = 0x00000000
    TRAP = 0x00030000
    ERRNO = 0x00050000

class SeccompFilter:
    """
    Apply seccomp-bpf filters to block dangerous syscalls
    Prevents privilege escalation and system tampering
    """

    def __init__(self):
        self.libc = ctypes.CDLL(ctypes.util.find_library("c"))

    async def apply_filter(self, band: str) -> bool:
        """
        Apply seccomp filter for privacy band (<1ms)
        Returns True if successful
        """
        if band == "BLACK":
            return await self._apply_no_syscalls()
        elif band == "RED":
            return await self._apply_red_band_filter()
        elif band in ["GREEN", "AMBER"]:
            return await self._apply_standard_filter()
        else:
            logger.error(f"Unknown band: {band}")
            return False

    async def _apply_standard_filter(self) -> bool:
        """GREEN/AMBER: Block dangerous syscalls"""
        blocked_syscalls = [
            # System tampering
            "mount",
            "umount",
            "umount2",
            "pivot_root",
            "chroot",
            "reboot",
            "swapon",
            "swapoff",

            # Privilege escalation
            "ptrace",
            "process_vm_readv",
            "process_vm_writev",
            "setuid",
            "setgid",
            "setreuid",
            "setregid",

            # Kernel modules
            "init_module",
            "finit_module",
            "delete_module",

            # Raw network
            "socket(AF_PACKET)",

            # Device access
            "ioctl(TIOCSTI)",
            "ioperm",
            "iopl"
        ]

        return self._load_filter(blocked_syscalls)

    async def _apply_red_band_filter(self) -> bool:
        """RED: Block most syscalls, allow minimal I/O"""
        allowed_syscalls = [
            # Essential I/O
            "read",
            "write",
            "open",
            "close",
            "stat",
            "fstat",
            "lseek",

            # Memory management
            "mmap",
            "munmap",
            "brk",

            # Process control
            "exit",
            "exit_group",

            # Signals
            "rt_sigaction",
            "rt_sigprocmask"
        ]

        # Default deny, allow only listed
        return self._load_allowlist_filter(allowed_syscalls)

    async def _apply_no_syscalls(self) -> bool:
        """BLACK: Block all syscalls (process will immediately fail)"""
        # Load filter that kills process on any syscall
        return self._load_kill_all_filter()

    def _load_filter(self, blocked_syscalls: List[str]) -> bool:
        """Load seccomp-bpf filter to block specific syscalls"""
        try:
            # Use libseccomp for easier filter management
            import seccomp

            f = seccomp.SyscallFilter(defaction=seccomp.ALLOW)

            for syscall_name in blocked_syscalls:
                syscall_num = seccomp.resolve_syscall(
                    seccomp.Arch.NATIVE,
                    syscall_name.split("(")[0]  # Handle "socket(AF_PACKET)" format
                )
                f.add_rule(seccomp.ERRNO(1), syscall_num)

            f.load()
            logger.info(f"Loaded seccomp filter: blocked {len(blocked_syscalls)} syscalls")
            return True

        except Exception as e:
            logger.error(f"Failed to load seccomp filter: {e}")
            return False

    def _load_allowlist_filter(self, allowed_syscalls: List[str]) -> bool:
        """Load seccomp filter with allowlist (default deny)"""
        try:
            import seccomp

            f = seccomp.SyscallFilter(defaction=seccomp.KILL)

            for syscall_name in allowed_syscalls:
                syscall_num = seccomp.resolve_syscall(
                    seccomp.Arch.NATIVE,
                    syscall_name
                )
                f.add_rule(seccomp.ALLOW, syscall_num)

            f.load()
            logger.info(f"Loaded allowlist filter: {len(allowed_syscalls)} syscalls")
            return True

        except Exception as e:
            logger.error(f"Failed to load allowlist filter: {e}")
            return False

    def _load_kill_all_filter(self) -> bool:
        """Load filter that kills process on any syscall"""
        try:
            import seccomp

            f = seccomp.SyscallFilter(defaction=seccomp.KILL)
            f.load()

            logger.info("Loaded kill-all seccomp filter (BLACK band)")
            return True

        except Exception as e:
            logger.error(f"Failed to load kill-all filter: {e}")
            return False
```

### Path Traversal Prevention

```python
# File: k1/security/path_validator.py

from pathlib import Path
from typing import Optional

class PathValidator:
    """
    Validate filesystem paths to prevent traversal attacks
    Enforces allowed/blocked path policies
    """

    def __init__(self, jail_root: Path):
        self.jail_root = jail_root.resolve()

    def validate_path(
        self,
        requested_path: str,
        allowed_paths: List[str],
        blocked_paths: List[str]
    ) -> Optional[Path]:
        """
        Validate requested path against policy
        Returns resolved path if valid, None if blocked
        """
        try:
            # Resolve path (handles .., symlinks)
            resolved = (self.jail_root / requested_path.lstrip("/")).resolve()

            # Check if still within jail
            if not str(resolved).startswith(str(self.jail_root)):
                logger.warning(
                    f"Path traversal attempt blocked",
                    requested=requested_path,
                    resolved=str(resolved)
                )
                return None

            # Check against blocked paths
            for blocked_pattern in blocked_paths:
                if self._matches_pattern(resolved, blocked_pattern):
                    logger.warning(
                        f"Blocked path access",
                        path=str(resolved),
                        pattern=blocked_pattern
                    )
                    return None

            # Check against allowed paths
            for allowed_pattern in allowed_paths:
                if self._matches_pattern(resolved, allowed_pattern):
                    return resolved

            # Not in allowed list
            logger.warning(
                f"Path not in allowed list",
                path=str(resolved)
            )
            return None

        except Exception as e:
            logger.error(f"Path validation error: {e}")
            return None

    def _matches_pattern(self, path: Path, pattern: str) -> bool:
        """Check if path matches wildcard pattern"""
        if pattern == "*":
            return True

        pattern_path = self.jail_root / pattern.lstrip("/")
        return str(path).startswith(str(pattern_path))
```

---

## Implementation Timeline

### Phase 1: chroot Jails (Weeks 1-3)
- **Week 1:** Jail template creation for GREEN/AMBER/RED bands
- **Week 2:** Bind mount management and read-only enforcement
- **Week 3:** Path traversal prevention and validation

### Phase 2: seccomp Filters (Weeks 4-6)
- **Week 4:** seccomp-bpf filter implementation
- **Week 5:** Syscall allowlist/blocklist per band
- **Week 6:** Filter loading and enforcement

### Phase 3: Integration (Weeks 7-8)
- **Week 7:** Jail lifecycle management (create/destroy)
- **Week 8:** WARD tests + validation

---

## Consequences

### Positive
1. **100% Path Traversal Prevention:** Symlinks and .. resolved, blocked
2. **Dangerous Syscalls Blocked:** ptrace, mount, reboot cannot be called
3. **Ephemeral Jails:** Clean slate per tool execution
4. **Kernel-Level Enforcement:** Cannot be bypassed

### Negative
1. **Root Privileges Required:** chroot and seccomp need CAP_SYS_CHROOT/CAP_SYS_ADMIN
2. **Jail Setup Overhead:** 3ms per tool (template copy + mount)
3. **Disk Space:** Each jail ~50MB (system libs + binaries)

### Risks
1. **Jail Escape:** Exploits in kernel could allow escape
   - Mitigation: Keep kernel updated, use seccomp as second layer
2. **Legitimate Tools Broken:** Overly restrictive filters
   - Mitigation: Per-tool whitelist testing

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Path Traversal Blocks | 100% | Zero successful traversals |
| Jail Setup Latency | <3ms | chroot + mount time |
| Syscall Block Rate | 100% | Blocked syscalls never execute |
| Jail Cleanup Time | <100ms | Unmount + delete time |

---

## Related Documents

- [ADR-0032: Band-Based Egress Rules](0032-band-based-egress-rules.md)
- [ADR-0032a: Network Egress Control](0032a-network-egress-control-iptables-privacy-bands.md)
- [ADR-0032c: Resource Egress Control](0032c-resource-egress-control-cgroups.md)
- [ADR-0032d: Egress Violation Logging](0032d-egress-violation-logging-audit-trail.md)

---

**Status:** ✅ Ready for implementation
**Timeline:** 8 weeks
**Priority:** ⭐⭐⭐ Critical (Security foundation)
