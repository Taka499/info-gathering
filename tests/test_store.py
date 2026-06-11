from infobot.models import Item
from infobot.store import Store


def make_item(i: int) -> Item:
    return Item(
        id=f"test:{i}",
        url=f"https://example.com/{i}",
        title=f"title {i}",
        source="test",
        category="tech-news",
    )


def test_filter_new_returns_items_then_nothing(tmp_path):
    store = Store(str(tmp_path / "seen.db"))
    items = [make_item(1), make_item(2)]
    assert store.filter_new(items) == items
    assert store.filter_new(items) == []


def test_filter_new_dedups_within_a_batch(tmp_path):
    store = Store(str(tmp_path / "seen.db"))
    items = [make_item(1), make_item(1)]
    assert store.filter_new(items) == [items[0]]


def test_state_persists_across_reopen(tmp_path):
    db = str(tmp_path / "seen.db")
    store = Store(db)
    items = store.filter_new([make_item(1)])
    store.mark_posted(items)
    store.close()

    reopened = Store(db)
    assert reopened.filter_new([make_item(1)]) == []
    row = reopened._conn.execute(
        "SELECT posted_utc FROM items WHERE id = 'test:1'"
    ).fetchone()
    assert row[0] is not None
    reopened.close()
