import inspect

from ninjos_backpacks.plugin import NinjOSBackpacks


def test_backpacks_does_not_patch_or_register_inventoryui_listener():
    source = inspect.getsource(NinjOSBackpacks.on_enable)

    assert "_handle_ping" not in source
    assert "UIListener" not in source
    assert "register_events(self)" in source
