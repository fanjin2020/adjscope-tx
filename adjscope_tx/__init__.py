"""Reusable diagnostics and reproducible workflows for transcriptomic adjustment."""

__version__ = '3.4.0'
__all__ = ['diagnose_design', 'compare_models', 'WorkflowConfig', 'run_workflow',
           'randomization_test', 'contrast_direction', 'restricted_allocations',
           'information_screen', 'wls_map']


def diagnose_design(exposure, groups, covariates=None):
    """Return outcome-free estimability and information diagnostics."""
    from .diagnostics import diagnose_design as implementation
    return implementation(exposure, groups, covariates)


def compare_models(response, baseline, adjusted, **kwargs):
    """Compare nested WLS models on the same samples and response matrix."""
    from .diagnostics import compare_models as implementation
    return implementation(response, baseline, adjusted, **kwargs)


def __getattr__(name):
    if name in ('WorkflowConfig', 'run_workflow'):
        from . import workflow
        return getattr(workflow, name)
    if name in ('randomization_test', 'contrast_direction',
                'restricted_allocations', 'information_screen', 'wls_map'):
        from . import randomization
        return getattr(randomization, name)
    raise AttributeError(name)
