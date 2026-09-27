# Provider contract harness

The shared suite iterates the production registry plus two test-only strategies.
The second fake uses a different origin and Bearer authentication to guard against
accidentally coupling the harness to one provider's wire format.

When adding an adapter in stage 04, add a `ContractCase` entry in `cases.py` backed
by that adapter's documented fixtures. It configures mock success/error/timeout
exchanges and checks authentication; shared assertions remain provider-neutral.
A registered provider with no case fails rather than silently skipping coverage.

HTTP-base implementation details (default timeouts, retry-date parsing, exact
metadata logs and preserved raw bodies) are tested in `../test_http_base.py`.
