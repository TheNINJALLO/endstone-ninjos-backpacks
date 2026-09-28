import inspect
import subprocess
import sys

from ninjos_backpacks.plugin import NinjOSBackpacks


def test_backpacks_does_not_patch_or_register_inventoryui_listener():
    source = inspect.getsource(NinjOSBackpacks.on_enable)

    assert "_handle_ping" not in source
    assert "UIListener" not in source
    assert "register_events(self)" in source


def test_import_does_not_patch_shared_protocol_or_require_it():
    code = '''
import importlib.abc
import sys
attempts = []
class RejectSharedProtocol(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "bedrock_protocol" or fullname.startswith("bedrock_protocol."):
            attempts.append(fullname)
            raise AssertionError("Backpacks tried to patch the shared protocol")
sys.meta_path.insert(0, RejectSharedProtocol())
from ninjos_backpacks import NinjOSBackpacks
assert NinjOSBackpacks.depend == ["inventoryui"]
assert not attempts, attempts
assert not any(n.startswith("bedrock_protocol") for n in sys.modules)
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
