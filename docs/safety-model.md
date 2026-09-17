# ReWoo Safety Model

## Overview

ReWoo's safety model is its core differentiator. While other agent frameworks execute reactively with no preview of what will happen, ReWoo shows you the full execution plan before any tool call runs.

## Risk Classification

Every plan step is classified into one of four risk levels:

| Level | Description | Approval Required | Example |
|-------|-------------|-------------------|---------|
| LOW | Read-only operations with no side effects | No | Reading a file, web search |
| MEDIUM | Operations with limited side effects | No (in auto mode) | Running a shell command, writing a file |
| HIGH | Operations with significant side effects | Yes | Deleting files, running sudo commands |
| CRITICAL | Irreversible or system-wide operations | Yes | rm -rf, formatting disks |

## Classification Signals

The Risk Classifier uses multiple signals:

1. **Tool defaults:** Each tool has an inherent risk level
2. **Argument patterns:** Regex matching for dangerous patterns
3. **Description keywords:** Natural language risk indicators
4. **Privilege escalation:** Detection of sudo, admin operations

## Approval Gates

### CLI Gate
Interactive terminal-based approval. Shows each step and prompts for y/N/edit/skip.

### Auto Gate
Automated approval with risk-based logic. LOW/MEDIUM auto-approved, HIGH/CRITICAL approved with warning in auto mode.

### None Gate
All steps approved automatically. Use only in trusted environments.

## Sandbox

Destructive operations run in a sandboxed environment:

- **Shell commands:** Run in subprocess with timeout, blocked patterns
- **File operations:** Path-restricted to allowed directories
- **Web requests:** Domain allowlist enforced

## Audit Trail

All execution events are written to an immutable JSONL log:

- Plan creation with all steps
- Approval/rejection decisions
- Step execution results
- Final synthesis output

This enables full reconstruction of any execution for debugging or compliance purposes.
