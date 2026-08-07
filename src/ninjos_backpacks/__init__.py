# Dynamic packet compat patch for bedrock-protocol & endstone-inventoryui
import sys
from types import ModuleType
from typing import Optional, List
from bstream import BinaryStream, ReadOnlyBinaryStream

try:
    import bedrock_protocol
    import bedrock_protocol.packets.packet as packet_module
    from bedrock_protocol.packets.packet.packet_base import Packet
    from bedrock_protocol.packets.minecraft_packet_ids import MinecraftPacketIds
    from bedrock_protocol.packets.types.full_container_name import FullContainerName

    # 1. Define and inject ItemStackResponseSlotInfo
    class ItemStackResponseSlotInfo:
        slot: int
        hotbar_slot: int
        count: int
        item_stack_id: int
        custom_name: str
        filtered_custom_name: str
        durability_correction: int

        def __init__(
            self,
            slot: int = 0,
            hotbar_slot: int = 0,
            count: int = 0,
            item_stack_id: int = 0,
            custom_name: str = "",
            filtered_custom_name: str = "",
            durability_correction: int = 0,
        ):
            self.slot = slot
            self.hotbar_slot = hotbar_slot
            self.count = count
            self.item_stack_id = item_stack_id
            self.custom_name = custom_name
            self.filtered_custom_name = filtered_custom_name
            self.durability_correction = durability_correction

        def write(self, stream: BinaryStream) -> None:
            stream.write_byte(self.slot)
            stream.write_byte(self.hotbar_slot)
            stream.write_byte(self.count)
            stream.write_varint(self.item_stack_id)
            stream.write_string(self.custom_name)
            stream.write_string(self.filtered_custom_name)
            stream.write_varint(self.durability_correction)

        def read(self, stream: ReadOnlyBinaryStream) -> None:
            self.slot = stream.get_byte()
            self.hotbar_slot = stream.get_byte()
            self.count = stream.get_byte()
            self.item_stack_id = stream.get_varint()
            self.custom_name = stream.get_string()
            self.filtered_custom_name = stream.get_string()
            self.durability_correction = stream.get_varint()

    # 2. Define and inject ItemStackResponseContainerInfo
    class ItemStackResponseContainerInfo:
        container: FullContainerName
        slots: List[ItemStackResponseSlotInfo]

        def __init__(
            self,
            container: Optional[FullContainerName] = None,
            slots: Optional[List[ItemStackResponseSlotInfo]] = None,
        ):
            self.container = container or FullContainerName()
            self.slots = slots or []

        def write(self, stream: BinaryStream) -> None:
            self.container.write(stream)
            stream.write_unsigned_varint(len(self.slots))
            for info in self.slots:
                info.write(stream)

        def read(self, stream: ReadOnlyBinaryStream) -> None:
            self.container.read(stream)
            length = stream.get_unsigned_varint()
            self.slots = []
            for _ in range(length):
                info = ItemStackResponseSlotInfo()
                info.read(stream)
                self.slots.append(info)

    # 3. Define and inject ItemStackResponse
    class ItemStackResponse:
        RESULT_OK = 0
        RESULT_ERROR = 1

        result: int
        request_id: int
        container_infos: List[ItemStackResponseContainerInfo]

        def __init__(
            self,
            result: int = 0,
            request_id: int = 0,
            container_infos: Optional[List[ItemStackResponseContainerInfo]] = None,
        ):
            self.result = result
            self.request_id = request_id
            self.container_infos = container_infos or []

        def write(self, stream: BinaryStream) -> None:
            stream.write_byte(self.result)
            stream.write_varint(self.request_id)
            if self.result == 0:  # RESULT_OK
                stream.write_unsigned_varint(len(self.container_infos))
                for info in self.container_infos:
                    info.write(stream)

        def read(self, stream: ReadOnlyBinaryStream) -> None:
            self.result = stream.get_byte()
            self.request_id = stream.get_varint()
            self.container_infos = []
            if self.result == 0:
                length = stream.get_unsigned_varint()
                for _ in range(length):
                    info = ItemStackResponseContainerInfo()
                    info.read(stream)
                    self.container_infos.append(info)

    # 4. Define and inject ItemStackResponsePacket
    class ItemStackResponsePacket(Packet):
        responses: List[ItemStackResponse]

        def __init__(self, responses: Optional[List[ItemStackResponse]] = None):
            super().__init__()
            self.responses = responses or []

        def get_packet_id(self) -> int:
            try:
                return int(MinecraftPacketIds.ItemStackResponse)
            except Exception:
                return 148

        def get_packet_name(self) -> str:
            return "ItemStackResponse"

        def write(self, stream: BinaryStream) -> None:
            stream.write_unsigned_varint(len(self.responses))
            for resp in self.responses:
                resp.write(stream)

        def read(self, stream: ReadOnlyBinaryStream) -> None:
            length = stream.get_unsigned_varint()
            self.responses = []
            for _ in range(length):
                resp = ItemStackResponse()
                resp.read(stream)
                self.responses.append(resp)

    # 5. Inject ItemStackResponsePacket into bedrock_protocol.packets.packet
    if not hasattr(packet_module, "ItemStackResponsePacket"):
        setattr(packet_module, "ItemStackResponsePacket", ItemStackResponsePacket)

    # 6. Define and Inject NetworkStackLatencyPacket if missing
    class NetworkStackLatencyPacket(Packet):
        timestamp: int
        from_server: bool

        def __init__(self, timestamp: int = 0, from_server: bool = False):
            super().__init__()
            self.timestamp = timestamp
            self.from_server = from_server

        def get_packet_id(self) -> int:
            try:
                return int(MinecraftPacketIds.Ping)
            except Exception:
                return 115

        def get_packet_name(self) -> str:
            return "NetworkStackLatencyPacket"

        def write(self, stream: BinaryStream) -> None:
            stream.write_unsigned_int64(self.timestamp)
            stream.write_bool(self.from_server)

        def read(self, stream: ReadOnlyBinaryStream) -> None:
            self.timestamp = stream.get_unsigned_int64()
            self.from_server = stream.get_bool()

    if not hasattr(packet_module, "NetworkStackLatencyPacket"):
        setattr(packet_module, "NetworkStackLatencyPacket", NetworkStackLatencyPacket)

    # 7. Inject types into sys.modules namespace
    types_mod_name = "bedrock_protocol.packets.types.item_stack_response"
    if types_mod_name not in sys.modules:
        m = ModuleType(types_mod_name)
        m.ItemStackResponse = ItemStackResponse
        m.ItemStackResponseContainerInfo = ItemStackResponseContainerInfo
        m.ItemStackResponseSlotInfo = ItemStackResponseSlotInfo
        sys.modules[types_mod_name] = m

except Exception as e:
    # Fail silently to avoid breaking general imports if bedrock_protocol is not present
    pass

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
