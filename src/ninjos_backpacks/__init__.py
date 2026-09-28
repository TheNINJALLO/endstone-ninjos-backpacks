# Apply runtime patches for endstone-inventoryui NBT preservation
try:
    import builtins
    if not hasattr(builtins, "Menu"):
        builtins.Menu = type("Menu", (), {})

    import endstone_inventoryui.util.item_utils as ui_item_utils
    import endstone_inventoryui.network.item_stack_wrapper as ui_wrapper
    from endstone.inventory import ItemStack
    import rapidnbt
    import sys

    # 1. Define recursive NBT converter
    def endstone_nbt_to_rapidnbt(tag):
        if tag is None:
            return None
        class_name = tag.__class__.__name__

        if class_name == "CompoundTag":
            r_tag = rapidnbt.CompoundTag()
            for k, v in tag.items():
                converted = endstone_nbt_to_rapidnbt(v)
                if converted is not None:
                    r_tag.set(k, converted)
            return r_tag
        elif class_name == "ListTag":
            r_tag = rapidnbt.ListTag()
            for i in range(tag.size()):
                converted = endstone_nbt_to_rapidnbt(tag[i])
                if converted is not None:
                    r_tag.append(converted)
            return r_tag
        elif class_name == "ByteTag":
            return rapidnbt.ByteTag(int(tag.value))
        elif class_name == "ShortTag":
            return rapidnbt.ShortTag(int(tag.value))
        elif class_name == "IntTag":
            return rapidnbt.IntTag(int(tag.value))
        elif class_name == "LongTag":
            return rapidnbt.LongTag(int(tag.value))
        elif class_name == "FloatTag":
            return rapidnbt.FloatTag(float(tag.value))
        elif class_name == "DoubleTag":
            return rapidnbt.DoubleTag(float(tag.value))
        elif class_name == "StringTag":
            return rapidnbt.StringTag(str(tag.value))
        elif class_name == "ByteArrayTag":
            return rapidnbt.ByteArrayTag(list(tag))
        elif class_name == "IntArrayTag":
            return rapidnbt.IntArrayTag(list(tag))
        else:
            if hasattr(tag, "value"):
                return rapidnbt.StringTag(str(tag.value))
            return rapidnbt.StringTag(str(tag))

    # 2. Patch clone_item
    original_clone_item = ui_item_utils.clone_item
    def patched_clone_item(item_stack: ItemStack) -> ItemStack:
        new_item = original_clone_item(item_stack)
        try:
            nbt = item_stack.nbt
            if nbt is not None:
                from ninjos_backpacks.serializer import nbt_to_dict, dict_to_nbt
                nbt_dict = nbt_to_dict(nbt)
                new_item.nbt = dict_to_nbt(nbt_dict)
        except Exception:
            pass
        return new_item

    ui_item_utils.clone_item = patched_clone_item

    # Patch in modules that might have already imported it
    if "endstone_inventoryui.util.item_utils" in sys.modules:
        sys.modules["endstone_inventoryui.util.item_utils"].clone_item = patched_clone_item
    if "endstone_inventoryui.menu.inventory" in sys.modules:
        sys.modules["endstone_inventoryui.menu.inventory"].clone_item = patched_clone_item
    if "endstone_inventoryui.manager.container.transaction_container" in sys.modules:
        sys.modules["endstone_inventoryui.manager.container.transaction_container"].clone_item = patched_clone_item
    if "endstone_inventoryui.manager.container.container_manager" in sys.modules:
        sys.modules["endstone_inventoryui.manager.container.container_manager"].clone_item = patched_clone_item

    # 3. Patch ItemStackWrapper.write_footer
    original_write_footer = ui_wrapper.ItemStackWrapper.write_footer
    def patched_write_footer(self, stream):
        try:
            item_meta = self.item_stack.item_meta
            tag = ui_item_utils.build_tag(item_meta)
            try:
                nbt = self.item_stack.nbt
                if nbt is not None:
                    custom_tag = endstone_nbt_to_rapidnbt(nbt)
                    if custom_tag is not None:
                        tag.merge(custom_tag)
            except Exception:
                pass

            if not tag.empty():
                stream.write_signed_short(-1)  # nbt length
                stream.write_byte(1)  # nbt version?
                stream.write_raw_bytes(tag.to_binary_nbt())
            else:
                stream.write_signed_short(0)  # no nbt

            stream.write_unsigned_int(0)  # canPlaceOn count
            stream.write_unsigned_int(0)  # canDestroy count
        except Exception:
            original_write_footer(self, stream)

    ui_wrapper.ItemStackWrapper.write_footer = patched_write_footer

except Exception:
    pass

from ninjos_backpacks.plugin import NinjOSBackpacks

__all__ = ["NinjOSBackpacks"]
