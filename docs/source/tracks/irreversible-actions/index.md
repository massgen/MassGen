# Irreversible Actions Track

**Lead:** Franklin | **Status:** 🟢 Active | **Updated:** 2025-01-15

**Mission:** Ensure MassGen agents operate safely, preventing irreversible or dangerous actions while maintaining flexibility.

---

## 🎯 Current Sprint (v0.0.30)

### P0 - Critical
- [ ] Security audit of permission system
- [ ] Test path traversal attack vectors

### P1 - High
- [ ] Implement rollback for file operations
- [ ] Add user confirmation for dangerous operations
- [ ] Document security best practices

### P2 - Medium
- [ ] Workspace quota enforcement
- [ ] Enhanced audit logging
- [ ] Permission inheritance rules

---

## 🔄 In Progress

### Parallel Execution Safety
**Status:** Active development | **Assignee:** Franklin | **Priority:** P0

Addressing irreversible actions when multiple agents work in parallel and preventing dangerous operations during concurrent execution.

**Key Areas:**
- Minority voting problem: ensuring dissenting agents can prevent dangerous actions
- Parallel execution coordination: preventing race conditions
- HSR (Harmonized Safety Review) draft stage implementation

### Rollback Mechanisms
**Status:** Design phase | **Assignee:** Franklin | **Priority:** P1

Enable undo for filesystem operations.

**Note:** v0.0.29 delivered FileOperationTracker (read-before-delete), which provides a safety layer. Full rollback capability (snapshots) is still in design phase.

**Design:**
- Snapshot files before modification
- Store in `.massgen/rollback/`
- Time-based cleanup (keep 24h)
- Undo command for users

### Security Audit
**Status:** Planning | **Assignee:** Open | **Priority:** P0

Comprehensive security review of permission system.

**Scope:**
- Path traversal vulnerabilities
- Permission bypass attempts
- Credential leak prevention
- Audit log integrity

---

## ✅ Recently Completed

- [x] FileOperationTracker implemented (v0.0.29 - read-before-delete safety)
- [x] Protected paths implemented (v0.0.26)
- [x] Permission system enhanced (v0.0.27)
- [x] Operation tracking added (v0.0.28)
- [x] Context paths (read-only access, v0.0.29)

---

## 🚧 Blocked

None currently

---

## 📝 Notes & Decisions Needed

**Discussion Topics:**
- Should rollback be automatic or manual?
- How long to keep rollback snapshots?
- User confirmation UX for dangerous operations

**Key Safety Mechanisms:**
- Protected path enforcement
- Permission validation before operations
- Operation tracking and logging
- Read-before-delete enforcement (v0.0.29)

**Known Risks:**
- **High:** Path traversal, credential leakage, data destruction
- **Medium:** Resource exhaustion, infinite loops
- **Low:** Log tampering, permission bypass

---

## Track Information

### Scope

**In Scope:**
- Filesystem permission system
- Protected paths and resources
- Operation validation and confirmation
- Rollback mechanisms
- Audit logging
- Safety guardrails
- User confirmation flows

**Out of Scope (For Now):**
- Network traffic filtering
- External API rate limiting
- Resource quotas (CPU, memory)
- Sandboxing/containerization

### Permission System

**Path Permissions:**
```yaml
filesystem:
  protected_paths:
    - path: "important_data/"
      permission: "read"         # Read-only
    - path: ".git/"
      permission: "none"         # No access
  context_paths:
    - path: "src/"
      permission: "read"         # Read-only source
```

**Implemented:**
- ✅ Protected path enforcement
- ✅ Permission validation before operations
- ✅ Operation tracking and logging
- ✅ Read-before-delete enforcement (v0.0.29)
- 🔄 Rollback mechanisms (in progress)

### File Operation Tracker

**Code:** `massgen/filesystem_manager/_file_operation_tracker.py`

**Features:**
- Log all filesystem operations
- Track which agent performed action
- Timestamp all operations
- Enable audit trail
- Read-before-delete enforcement

### Path Permission Manager

**Code:** `massgen/filesystem_manager/_path_permission_manager.py`

**Features:**
- Check permissions before operations
- Prevent unauthorized access
- Support for wildcards and patterns
- Hierarchical permission inheritance

### Security Model

**Principles:**
1. **Least Privilege:** Agents get minimum necessary permissions
2. **Defense in Depth:** Multiple layers of protection
3. **Fail Safe:** Default to deny access
4. **Audit Trail:** Log everything for accountability
5. **User Control:** User can override when needed

**Trust Boundaries:**
- **Workspace:** Agent has full control
- **Context Paths:** Read-only access
- **Protected Paths:** Restricted or no access
- **System:** No access by default

### Pre-Operation Validation

1. **Permission Check:** Verify agent has permission
2. **Path Validation:** Ensure path is safe
3. **Operation Type:** Validate operation is allowed
4. **Confirmation:** Request user confirmation (if configured)

### Post-Operation Tracking

1. **Log Operation:** Record what happened
2. **State Snapshot:** Capture before/after state
3. **Rollback Point:** Enable undo if needed

### Dangerous Operations

Currently blocked or require confirmation:
- Deleting files outside workspace
- Modifying system files
- Accessing credentials/secrets
- Network operations (future)
- Code execution (future, with sandbox)

### Team & Resources

**Contributors:** Open to community contributors, security reviewers needed
**GitHub Label:** `track:safety`, `security`
**Code:** `massgen/filesystem_manager/`
**Tests:** `massgen/tests/test_*permission*.py`
**Examples:** `massgen/configs/tools/filesystem/*permissions*.yaml`

**Related Tracks:**
- **Coding Agent:** Implements file operations with safety checks
- **All Tracks:** Safety applies to all agent operations

### Dependencies

**Internal:**
- `massgen.filesystem_manager` - Core implementation
- `massgen.orchestrator` - Operation coordination
- `massgen.backend` - Agent command validation

**External:**
- Python os/pathlib security features
- File system permissions
- Operating system security

---

## Long-Term Vision

See **[roadmap.md](./roadmap.md)** for 3-6 month goals including comprehensive rollback, resource quotas, and advanced safety mechanisms.

---

**Responsible Disclosure:** If you find a security vulnerability, do not create a public issue. Email security contact with details and reproduction steps.

---

*Track lead: Update sprint section weekly. Update long-term vision in roadmap.md monthly.*
