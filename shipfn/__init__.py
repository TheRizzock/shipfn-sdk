"""Shipfn SDK: mark functions with @deploy and push the repo; the platform does the rest."""
from shipfn.decorator import DeployedFunction, deploy, registry

__version__ = "0.1.0"
__all__ = ["deploy", "DeployedFunction", "registry", "__version__"]
