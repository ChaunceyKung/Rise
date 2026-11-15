"""Packaged immutable pricing, trust and runtime pins. No code execution."""
from importlib.resources import files

def data_path(group, name):
    """Return a package-relative read-only resource locator, independent of cwd."""
    if (group, name) not in {("pricing", "readiness_quote.json"), ("trust", "evaluation_history.json"), ("trust", "task_diagnostic_trust.json"), ("pins", "concordia.json"), ("pins", "c5_runtime.json")}:
        raise ValueError("unregistered resource")
    return files(__package__).joinpath(group, name)
