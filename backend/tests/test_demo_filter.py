from app.core.demo import is_demo_mapping, is_demo_record


def test_demo_owner_repo_and_display_names_are_filtered():
    assert is_demo_record(name="example/demo")
    assert is_demo_record(name="example/demo-8514b4b9")
    assert is_demo_record(display_name="Demo-add09101")
    assert is_demo_record(owner="example", repository_name="demo-3af0a446")
    assert is_demo_record(repository_url="https://github.com/example/demo-8631b7b2")


def test_real_repositories_are_kept():
    assert not is_demo_record(name="local/clientonboarding", owner="local", repository_name="clientonboarding")
    assert not is_demo_record(name="acme/widgets", owner="acme", repository_name="widgets")
    assert not is_demo_mapping({"name": "local/clientonboarding", "branch": "new-changes"})
