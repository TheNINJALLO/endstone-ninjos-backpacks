import json
import re
from typing import Optional, Dict, Any, List

from endstone.inventory import ItemStack

# Endstone 0.11 exports NBT tag classes from endstone.nbt.
from endstone.nbt import (
    CompoundTag, ListTag, ByteTag, ShortTag, IntTag, LongTag,
    FloatTag, DoubleTag, StringTag, ByteArrayTag, IntArrayTag,
)

def nbt_to_dict(tag) -> dict:
    """Recursively convert any NBT Tag to a JSON-serializable Python object."""
    if isinstance(tag, CompoundTag):
        return {
            "_type": "compound",
            "value": {k: nbt_to_dict(v) for k, v in tag.items()}
        }
    elif isinstance(tag, ListTag):
        return {
            "_type": "list",
            "value": [nbt_to_dict(tag[i]) for i in range(tag.size())]
        }
    elif isinstance(tag, ByteTag):
        return {"_type": "byte", "value": tag.value}
    elif isinstance(tag, ShortTag):
        return {"_type": "short", "value": tag.value}
    elif isinstance(tag, IntTag):
        return {"_type": "int", "value": tag.value}
    elif isinstance(tag, LongTag):
        return {"_type": "long", "value": tag.value}
    elif isinstance(tag, FloatTag):
        return {"_type": "float", "value": tag.value}
    elif isinstance(tag, DoubleTag):
        return {"_type": "double", "value": tag.value}
    elif isinstance(tag, StringTag):
        return {"_type": "string", "value": tag.value}
    elif isinstance(tag, ByteArrayTag):
        return {"_type": "byte_array", "value": list(tag)}
    elif isinstance(tag, IntArrayTag):
        return {"_type": "int_array", "value": list(tag)}
    else:
        return {"_type": "unknown", "value": str(tag)}

def dict_to_nbt(data):
    """Recursively rebuild an NBT Tag from a dict produced by nbt_to_dict."""
    t = data.get("_type", "unknown")
    v = data.get("value")

    if t == "compound":
        tag = CompoundTag()
        for key, child in v.items():
            tag[key] = dict_to_nbt(child)
        return tag
    elif t == "list":
        list_tag = ListTag()
        for child in v:
            list_tag.append(dict_to_nbt(child))
        return list_tag
    elif t == "byte":
        return ByteTag(int(v))
    elif t == "short":
        return ShortTag(int(v))
    elif t == "int":
        return IntTag(int(v))
    elif t == "long":
        return LongTag(int(v))
    elif t == "float":
        return FloatTag(float(v))
    elif t == "double":
        return DoubleTag(float(v))
    elif t == "string":
        return StringTag(str(v))
    elif t == "byte_array":
        return ByteArrayTag(v)
    elif t == "int_array":
        return IntArrayTag(v)
    else:
        return StringTag(str(v))

def serialize_item(item: ItemStack) -> Optional[dict]:
    """Serialize an ItemStack (or None/air) to a JSON-friendly dict."""
    if item is None or str(item.type) == "minecraft:air" or item.amount <= 0:
        return None

    result = {
        "type": str(item.type),
        "amount": item.amount,
    }

    # Save the full NBT compound tag — this preserves everything:
    # enchantments, lore, display name, durability/damage, custom metadata.
    try:
        nbt_tag = item.nbt
        if nbt_tag is not None:
            result["nbt"] = nbt_to_dict(nbt_tag)
    except Exception:
        pass

    return result

def deserialize_item(item_data: dict) -> Optional[ItemStack]:
    """Recreate an ItemStack from a dict produced by serialize_item."""
    if not item_data or item_data.get("type") is None:
        return None

    item_type = item_data["type"]
    amount = item_data.get("amount", 1)
    
    # Endstone limits ItemStack constructor amount to [1, 255]
    safe_amount = max(1, min(amount, 255))
    item = ItemStack(item_type, safe_amount)

    # Restore the full NBT compound tag
    nbt_data = item_data.get("nbt")
    if nbt_data is not None:
        try:
            tag = dict_to_nbt(nbt_data)
            if isinstance(tag, CompoundTag):
                item.nbt = tag
        except Exception:
            pass

    return item

def get_backpack_id_from_item(item: ItemStack) -> Optional[str]:
    """Extract backpack UUID from an item's lore if present."""
    if not item or str(item.type) == "minecraft:air":
        return None
    try:
        meta = item.item_meta
        if meta and meta.has_lore:
            for line in meta.lore:
                match = re.match(r"§8Backpack ID:\s*(.+)", line)
                if match:
                    return match.group(1).strip()
    except Exception:
        pass
    return None
