"""Force Renovate's base branches to main and the supported stable series."""

import json
import os
from pathlib import Path

from release_policy import supported_branches


def base_branches(api) -> list[str]:
    return ["main", *supported_branches(api)]


if __name__ == "__main__":
    from github_api import create_client

    force = json.dumps({"baseBranchPatterns": base_branches(create_client())})
    print(f"Renovate configuration override: {force}")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"force={force}\n")
