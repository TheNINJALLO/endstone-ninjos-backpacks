from types import SimpleNamespace

from ninjos_backpacks.manager import BackpackManager


class RecordingLogger:
    def __init__(self):
        self.errors = []

    def error(self, message):
        self.errors.append(message)

    def warning(self, _message):
        pass


class QueuedScheduler:
    def __init__(self):
        self.tasks = []

    def run_task(self, plugin, task, delay=0):
        self.tasks.append((plugin, task, delay))


def make_manager():
    scheduler = QueuedScheduler()
    plugin = SimpleNamespace(server=SimpleNamespace(scheduler=scheduler))
    manager = BackpackManager.__new__(BackpackManager)
    manager.plugin = plugin
    manager.logger = RecordingLogger()
    manager.active_pages = {"player-1": 0}
    manager.contents_caches = {"player-1": {}}
    manager.pending_page_changes = set()
    return manager, scheduler


def test_page_change_persists_repaints_and_resyncs_before_advancing_state():
    manager, scheduler = make_manager()
    player = SimpleNamespace(unique_id="player-1")
    menu = object()
    calls = []

    manager.supports_virtual_stacks = lambda _storage_id: False
    manager.save_current_page_to_cache = (
        lambda received_menu, page, cache: calls.append(("save", received_menu, page, cache))
    )
    manager.populate_menu_page = (
        lambda received_menu, page, total_pages, cache, storage_id: calls.append(
            ("populate", received_menu, page, total_pages, cache, storage_id)
        )
    )
    manager._resync_menu_contents = (
        lambda received_player, received_menu: calls.append(
            ("resync", received_player, received_menu)
        )
    )

    assert manager._schedule_page_change(player, menu, "backpack_large", 2, 1)
    assert manager.active_pages["player-1"] == 0
    assert "player-1" in manager.pending_page_changes
    assert scheduler.tasks[0][2] == 1

    scheduler.tasks[0][1]()

    assert manager.active_pages["player-1"] == 1
    assert "player-1" not in manager.pending_page_changes
    assert [call[0] for call in calls] == ["save", "populate", "resync"]


def test_page_change_failure_releases_guard_and_keeps_current_page():
    manager, scheduler = make_manager()
    player = SimpleNamespace(unique_id="player-1")

    manager.supports_virtual_stacks = lambda _storage_id: True
    manager.populate_menu_page = lambda *_args: (_ for _ in ()).throw(RuntimeError("redraw failed"))
    manager._resync_menu_contents = lambda *_args: None

    assert manager._schedule_page_change(player, object(), "block:overworld:1:2:3", 2, 1)
    scheduler.tasks[0][1]()

    assert manager.active_pages["player-1"] == 0
    assert "player-1" not in manager.pending_page_changes
    assert "redraw failed" in manager.logger.errors[0]


def test_page_change_rejects_out_of_bounds_and_duplicate_requests():
    manager, scheduler = make_manager()
    player = SimpleNamespace(unique_id="player-1")

    manager.supports_virtual_stacks = lambda _storage_id: True

    assert not manager._schedule_page_change(player, object(), "backpack_large", 2, -1)
    assert manager._schedule_page_change(player, object(), "backpack_large", 2, 1)
    assert not manager._schedule_page_change(player, object(), "backpack_large", 2, 1)
    assert len(scheduler.tasks) == 1
