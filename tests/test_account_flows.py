from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from diji.account_catalog import AccountCatalog
from diji.local_catalog import CharacterSpec, FlowSpec, LocalCatalog


def test_account_flows_override_defaults_without_copying_characters(tmp_path: Path) -> None:
    shared = LocalCatalog(tmp_path / "shared.json")
    alice = AccountCatalog(shared, tmp_path / "users" / "alice" / "catalog.json")
    bob = AccountCatalog(shared, tmp_path / "users" / "bob" / "catalog.json")
    default = shared.flow("immersive")
    assert alice.flow("immersive") == bob.flow("immersive") == default
    assert not alice.private.path.exists()

    character = CharacterSpec(id="alice-char", name="私人", premise="背景", voice="語氣")
    alice.private.save_character(character)
    alice.save_flow(default.model_copy(update={"name": "個人版本", "layers": ["scene"]}))
    alice.save_flow(FlowSpec(id="custom-flow", name="自訂"))

    assert alice.flow("immersive").name == "個人版本"
    assert bob.flow("immersive") == shared.flow("immersive") == default
    assert {flow.id for flow in bob.snapshot().flows} == {default.id}
    assert alice.private.snapshot().characters == [character]
    assert [item.id for item in alice.snapshot().characters] == ["yelan", "shenzhou", "alice-char"]
    assert not shared.path.exists()
    assert alice.private.path.stat().st_mode & 0o777 == 0o600
    assert alice.private.path.parent.stat().st_mode & 0o777 == 0o700
    assert alice.private.path.with_name("catalog.json.lock").stat().st_mode & 0o777 == 0o600


def test_parallel_character_and_flow_saves_keep_all_items(tmp_path: Path) -> None:
    shared = LocalCatalog(tmp_path / "shared.json")
    path = tmp_path / "users" / "alice" / "catalog.json"

    def save(index: int) -> None:
        account = AccountCatalog(shared, path)
        if index % 2:
            account.private.save_character(CharacterSpec(id=f"char-{index}", name="私人", premise="背景", voice="語氣"))
        else:
            account.save_flow(FlowSpec(id=f"flow-{index}", name="流程"))

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(save, range(20)))
    snapshot = LocalCatalog(path, empty_initial=True).snapshot()
    assert {item.id for item in snapshot.characters} == {f"char-{i}" for i in range(20) if i % 2}
    assert {item.id for item in snapshot.flows} == {f"flow-{i}" for i in range(20) if not i % 2}
