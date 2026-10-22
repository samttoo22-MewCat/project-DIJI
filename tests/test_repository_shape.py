from pathlib import Path


def test_source_tree_has_the_two_core_flows() -> None:
    root = Path(__file__).parents[1] / "src" / "diji"
    assert (root / "character_generation").is_dir()
    assert (root / "interaction").is_dir()


def test_runtime_and_image_generation_are_not_source_modules() -> None:
    root = Path(__file__).parents[1] / "src" / "diji"
    assert not (root / "image_generation").exists()
    assert not (root / "runtime").exists()
