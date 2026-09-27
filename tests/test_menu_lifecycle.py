from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ninjos_backpacks.manager import BackpackManager


@pytest.fixture
def backpack(monkeypatch):
    import ninjos_backpacks.manager as module
    menu = Mock()
    menu.inventory.get_item.return_value = None
    monkeypatch.setattr(module, "Menu", Mock(return_value=menu))
    monkeypatch.setattr(module, "get_backpack_id_from_item", lambda item: None)
    player = SimpleNamespace(unique_id="player-1", name="TestPlayer", send_message=Mock())
    callbacks = []
    scheduler = SimpleNamespace(run_task=lambda owner, callback, **kw: callbacks.append(callback))
    plugin = SimpleNamespace(
        db=Mock(), logger=Mock(), server=SimpleNamespace(scheduler=scheduler),
        cfg=SimpleNamespace(item_backpacks={"large": {"size": 90}}, rules={},
                            virtual_stacks={}, block_storage={"vault": {"size": 90}}),
    )
    plugin.db.get_item_backpack.return_value = {"contents": {}, "owner_uuid": "player-1"}
    manager = BackpackManager(plugin)
    manager.populate_menu_page = Mock()
    manager.supports_virtual_stacks = Mock(return_value=False)
    manager._resync_menu_contents = Mock()
    return manager, player, menu, callbacks


def test_aborted_open_releases_lock_without_overwriting_storage(backpack):
    manager, player, menu, _ = backpack
    manager.open_item_backpack(player, "pack-1", "large")
    assert manager.session_opened_successfully["player-1"] is False
    menu.set_close_listener.call_args.args[0](player)
    manager.db.save_item_backpack.assert_not_called()
    assert manager.active_item_sessions == {}
    assert manager.contents_caches == {}


def test_only_open_ack_allows_close_to_save(backpack):
    manager, player, menu, _ = backpack
    manager.open_item_backpack(player, "pack-1", "large")
    menu.set_open_listener.call_args.args[0](player)
    menu.set_close_listener.call_args.args[0](player)
    manager.db.save_item_backpack.assert_called_once()
    assert manager.active_item_sessions == {}


def test_pending_page_blocks_following_item_moves(backpack):
    manager, player, menu, callbacks = backpack
    manager.open_item_backpack(player, "pack-1", "large")
    listener = menu.set_listener.call_args.args[0]
    tr = SimpleNamespace(slot=53, player=player, item_clicked=None, item_clicked_with=None,
                         discard=Mock(return_value="discarded"), proceed=Mock())
    assert listener(tr) == "discarded"
    assert "player-1" in manager.pending_page_changes
    tr.slot = 0
    assert listener(tr) == "discarded"
    tr.proceed.assert_not_called()
    callbacks[0]()
    assert manager.active_pages["player-1"] == 1
    assert not manager.pending_page_changes


def test_second_storage_cannot_overwrite_first_menu_cache(backpack):
    manager, player, menu, _ = backpack
    manager.open_item_backpack(player, "pack-1", "large")
    first_cache = manager.contents_caches["player-1"]
    manager.open_item_backpack(player, "pack-2", "large")
    assert manager.contents_caches["player-1"] is first_cache
    assert manager.active_item_sessions == {"pack-1": "player-1"}
    menu.send_to.assert_called_once()


def test_partial_last_page_rejects_slots_above_configured_capacity(backpack):
    manager, player, menu, _ = backpack
    manager.config.item_backpacks["large"]["size"] = 60
    manager.open_item_backpack(player, "pack-1", "large")
    manager.active_pages["player-1"] = 1
    tr = SimpleNamespace(slot=15, player=player, item_clicked=None, item_clicked_with=None,
                         discard=Mock(return_value="discarded"), proceed=Mock())
    assert menu.set_listener.call_args.args[0](tr) == "discarded"
    tr.proceed.assert_not_called()
