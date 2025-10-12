# ADR-0002: Use PyTorch as Deep Learning Framework

**Status:** Accepted
**Date:** 2024-10-08 (decision made ~2024-06, documented retroactively)
**Deciders:** @Leezekun, core team
**Technical Story:** Foundation for ML model integration

## Context and Problem Statement

MassGen requires a deep learning framework for:
- Model loading and inference
- Integration with various LLM backends
- Potential future training capabilities
- Tool integrations that may use ML models
- Compatibility with the broader ML ecosystem

The framework choice is foundational and affects:
- Developer productivity and learning curve
- Model compatibility and ecosystem access
- Performance and optimization capabilities
- Integration with cloud providers
- Community support and resources

## Considered Options

1. **PyTorch** - Dynamic computation graphs, Pythonic API, strong ecosystem
2. **TensorFlow** - Google-backed, production-focused, mature tooling
3. **JAX** - NumPy-like API, powerful transformations, functional paradigm
4. **No framework** - Implement minimal needed functionality ourselves

## Decision

We chose **PyTorch**.

### Rationale

- **Pythonic and intuitive**: API feels natural to Python developers
- **Dynamic computation graphs**: Easier debugging and more flexible for research-style development
- **Ecosystem dominance**: Most frontier models released with PyTorch weights first
- **HuggingFace integration**: Seamless integration with transformers library
- **Research community**: Latest models and techniques typically in PyTorch
- **Growing production tooling**: TorchScript, TorchServe improving deployment story
- **CUDA optimization**: Excellent GPU support and optimization
- **Active development**: Strong backing from Meta and vibrant community

## Consequences

### Positive

- Easy integration with HuggingFace models and transformers
- Pythonic API reduces friction for contributors
- Dynamic graphs enable experimentation and debugging
- Strong community means abundant resources and examples
- Latest research models typically available in PyTorch first
- Good GPU memory management tools
- TorchScript provides path to production optimization

### Negative

- Historically weaker production deployment tools vs TensorFlow (though improving)
- Can have higher memory usage than some alternatives
- Dynamic graphs can make optimization harder
- Some enterprise environments prefer TensorFlow

### Neutral

- Need to learn PyTorch conventions and best practices
- GPU memory management requires attention
- Version compatibility must be managed

## Implementation Notes

- PyTorch primarily used for model loading and inference
- Integration with various LLM backends may use PyTorch models
- Transformer models loaded via HuggingFace transformers library
- Future multimodal capabilities will leverage PyTorch

Currently minimal direct PyTorch usage in core, but:
- Enables integration with PyTorch-based models
- Positions project for future ML tool integrations
- Aligns with broader ML community standards

## Validation

Success metrics:
- ✅ Can load and use PyTorch-based models when needed
- ✅ Compatible with HuggingFace ecosystem
- ✅ Contributors familiar with PyTorch can contribute easily
- ✅ No significant performance issues from framework choice

## Related Decisions

- Enables future multimodal capabilities
- Supports integration with various model backends
- May inform future training/fine-tuning features

## Notes

This decision was made early in the project based on:
- Team expertise with PyTorch
- Research community alignment
- Future-proofing for model integrations

The framework is used judiciously - MassGen focuses on orchestration rather than heavy ML operations, so framework choice has limited direct impact on current functionality but positions the project well for future enhancements.

---

*Last updated: 2024-10-08 by @ncrispin*
