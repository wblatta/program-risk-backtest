from adapters.base import AdapterConfig

REPOS = {
    "enhancements": "https://github.com/kubernetes/enhancements.git",
    "community": "https://github.com/kubernetes/community.git",
    "sig_release": "https://github.com/kubernetes/sig-release.git",
}
CONFIG = AdapterConfig(name="k8s", required_roles=("prr_approver",))
