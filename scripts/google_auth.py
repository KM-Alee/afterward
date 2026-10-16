"""Print one Google refresh token for a demo mailbox.

The operator runs this locally and stores the token in the platform environment.
This script does not write the token into the repository, and tests never start
the browser flow.

The browser returns to localhost. That redirect is only for minting the token.
A deployed app uses the refresh token and does not serve this redirect.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence

from app.integrations.google import SCOPES

FlowFactory = Callable[[str, Sequence[str]], object]


def main(argv: list[str] | None = None, *, flow_factory: FlowFactory | None = None) -> int:
    """Run the local OAuth flow and print only the refresh token."""
    parser = argparse.ArgumentParser(
        description="Print one mailbox refresh token. Nothing is written into the repo."
    )
    parser.add_argument(
        "--client",
        required=True,
        help="OAuth client file supplied by the operator",
    )
    parser.add_argument("--mailbox", required=True, choices=("family", "providers"))
    args = parser.parse_args(argv)
    factory = flow_factory or _installed_flow
    flow = factory(args.client, SCOPES)
    credentials = flow.run_local_server(port=0)  # type: ignore[attr-defined]
    token = getattr(credentials, "refresh_token", None)
    if not token:
        print("Google did not return a refresh token.", file=sys.stderr)
        return 1
    print(token)
    return 0


def _installed_flow(client_path: str, scopes: Sequence[str]) -> object:
    from google_auth_oauthlib.flow import InstalledAppFlow

    return InstalledAppFlow.from_client_secrets_file(client_path, list(scopes))


if __name__ == "__main__":
    raise SystemExit(main())
