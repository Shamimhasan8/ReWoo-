# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in ReWoo, please report it responsibly:

1. **Do not** open a public GitHub issue
2. Email security@rewoo.ai with details
3. Include steps to reproduce and potential impact
4. We will respond within 48 hours

## Security Model

ReWoo's security model is built on three layers:

### 1. Risk Classification
Every plan step is classified by risk level (LOW/MEDIUM/HIGH/CRITICAL) before execution. Steps classified as HIGH or CRITICAL require explicit approval.

### 2. Approval Gates
Human-in-the-loop approval ensures that destructive operations never execute without consent. The approval mode can be configured per execution.

### 3. Sandboxed Execution
Destructive tools run in sandboxed environments with:
- Path restrictions for file operations
- Command pattern blocking for shell operations
- Timeout enforcement
- Domain allowlists for web requests

## Known Limitations

- The sandbox is a subprocess-level restriction, not a container-level isolation
- Shell commands can bypass pattern matching with encoding tricks
- File path resolution may allow directory traversal in some configurations

## Best Practices

- Always use `REWOO_APPROVAL_MODE=cli` for production workloads
- Enable sandbox mode: `REWOO_SANDBOX_ENABLED=true`
- Review the audit log regularly: `rewoo audit`
- Set restrictive `file_allowed_paths` for file operations
- Use domain allowlists for web requests
