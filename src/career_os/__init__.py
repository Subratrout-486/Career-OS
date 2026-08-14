"""Career OS multi-agent runtime."""

# Install the Resume Library visibility fix before the orchestrator imports
# NotionReviewQueue. The patch preserves the existing API and only adds a
# visible page summary after a library record is created.
from . import notion_visibility  # noqa: F401,E402

# Keep Manus as the orchestration/browser layer while routing expensive
# analysis and resume work to specialist providers when configured.
from . import specialist_routing  # noqa: F401,E402

specialist_routing.install_specialist_routing()
