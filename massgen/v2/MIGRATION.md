# MassGen v0.0.2 Migration Plan

## Current Status: Safe Side-by-Side Development

The v0.0.2 architecture is currently in the `massgen.v2` namespace to ensure:

- **Zero breaking changes** to existing v0.0.1 users
- **Safe development** of new architecture
- **Gradual migration path** for users
- **Thorough testing** before replacing legacy system

## Usage During Development

### v0.0.1 (Legacy - Unchanged)
```python
from massgen import run_mass_agents, MassSystem, load_config_from_yaml
# All existing code continues to work exactly as before
```

### v0.0.2 (New Architecture)
```python
from massgen.v2 import create_simple_agent, ChatAgent, create_agent_team
# New architecture available for testing and development
```

## Migration Timeline

1. **Phase 1 ✅ Complete**: Core v0.0.2 foundation in `massgen.v2`
2. **Phase 2-5**: Continue development in `massgen.v2` namespace
3. **Future**: Once v0.0.2 is fully implemented and tested:
   - Gradually deprecate v0.0.1 APIs
   - Move v0.0.2 components to main `massgen` namespace
   - Provide migration guides and compatibility layers

## Benefits of This Approach

- **Risk-free development**: Old system unaffected during new development
- **User confidence**: No surprise breaking changes
- **Testing flexibility**: Can compare both architectures side-by-side
- **Rollback safety**: Can revert easily if issues discovered
- **Documentation time**: Can write migration guides before making changes

## When Migration is Complete

Eventually the structure will become:
```python
from massgen import create_simple_agent  # v0.0.2 becomes primary
from massgen.legacy import run_mass_agents  # v0.0.1 moves to legacy
```

But this won't happen until v0.0.2 is fully proven and documented.