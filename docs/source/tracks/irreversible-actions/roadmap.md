# Irreversible Actions Track - Roadmap

**Lead:** Franklin | **Last Updated:** 2025-01-15

> **Quick Update Template:** Project leads can update this file in <5 minutes

---

## 🎯 Current Sprint (v0.0.30)

**Target Date:** TBD

### Critical (P0)
- [ ] Security audit of permission system
- [ ] Test path traversal attack vectors

### High Priority (P1)
- [ ] Implement rollback for file operations
- [ ] Add user confirmation for dangerous operations
- [ ] Document security best practices

### Nice to Have (P2)
- [ ] Workspace quota enforcement
- [ ] Enhanced audit logging
- [ ] Permission inheritance rules

---

## 📅 Upcoming Milestones

| Milestone | Target | Status |
|-----------|--------|--------|
| Rollback mechanisms (snapshots) | 2025-10-31 | 🔄 In Progress |
| User confirmations | 2025-11-15 | 📋 Planned |
| Workspace quotas | 2025-11-30 | 📋 Planned |
| Secret detection | 2025-12-31 | 📋 Planned |
| Full sandboxing | 2026-02-28 | 🔮 Future |

---

## ✅ Recent Completions

- [x] FileOperationTracker implemented (v0.0.29 - read-before-delete safety)
- [x] Path Permission Manager enhancements (v0.0.29)
- [x] Protected paths implemented (v0.0.26)
- [x] Permission system enhanced (v0.0.27)
- [x] Operation tracking added (v0.0.28)

---

## 🚧 Blocked Items

None currently

---

## 💬 Quick Notes

**This Week:**
- Working on parallel execution safety mechanisms
- Addressing minority voting problem for dangerous actions

**Next Week:**
- Security audit planning
- Rollback mechanism design review

**Decisions Needed:**
- Should rollback be automatic or manual?
- How long to keep rollback snapshots?
- User confirmation UX for dangerous operations

**Known Risks:**
- **High:** Path traversal, credential leakage, data destruction
- **Medium:** Resource exhaustion, infinite loops
- **Low:** Log tampering, permission bypass

---

*See [details.md](./details.md) for architecture, dependencies, and long-term vision*
