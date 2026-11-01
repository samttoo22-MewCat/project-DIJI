"""Account-local catalog overrides layered over the shared defaults."""

from pathlib import Path

from .local_catalog import CatalogSnapshot, FlowSpec, LocalCatalog


class AccountCatalog:
    def __init__(self, defaults: LocalCatalog, private_path: Path) -> None:
        self.defaults = defaults
        self.private = LocalCatalog(private_path, empty_initial=True)

    def snapshot(self) -> CatalogSnapshot:
        shared = self.defaults.snapshot()
        private = self.private.snapshot()
        flows = {item.id: item for item in shared.flows}
        flows.update({item.id: item for item in private.flows})
        return CatalogSnapshot(characters=shared.characters + private.characters, flows=list(flows.values()))

    def flow(self, flow_id: str) -> FlowSpec:
        return next(item for item in self.snapshot().flows if item.id == flow_id)

    def save_flow(self, flow: FlowSpec) -> FlowSpec:
        return self.private.save_flow(flow)
