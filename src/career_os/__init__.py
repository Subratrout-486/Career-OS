"""Career OS multi-agent runtime."""

# Install the Resume Library visibility fix before the orchestrator imports
# NotionReviewQueue. The patch preserves the existing API and only adds a
# visible page summary after a library record is created.
from . import notion_visibility  # noqa: F401,E402

# Reconcile agent prompt policy against the current canonical resume and
# approved Career Evidence Vault before specialist_routing snapshots prompt
# constants. This prevents stale employer/tool denylists from overriding
# current confirmed evidence.
from . import truth_policy  # noqa: F401,E402

truth_policy.install_truth_policy()

# Keep Manus as the orchestration/browser layer while routing expensive
# analysis and resume work to specialist providers when configured.
from . import specialist_routing  # noqa: F401,E402

specialist_routing.install_specialist_routing()
