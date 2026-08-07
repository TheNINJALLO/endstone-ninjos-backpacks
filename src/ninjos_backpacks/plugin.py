from pathlib import Path
from typing import Dict, Any, List
import traceback

from endstone import Player, ColorFormat
from endstone.plugin import Plugin
from endstone.event import event_handler, PlayerInteractEvent, BlockPlaceEvent, BlockBreakEvent, PlayerQuitEvent, PlayerJoinEvent, PacketReceiveEvent
from endstone.command import Command, CommandSender
import time
from ninjos_backpacks.inv_manager import InventoryManagerUI

from ninjos_backpacks.config import Config
from ninjos_backpacks.database import Database
from ninjos_backpacks.manager import BackpackManager
from ninjos_backpacks.commands import CommandHandler
from ninjos_backpacks.serializer import get_backpack_id_from_item

def normalize_block_type(block_type: str) -> str:
    if not block_type:
        return ""
    return block_type.lower().replace("minecraft:", "")

class NinjOSBackpacks(Plugin):
    api_version = "0.11"
    load = "POSTWORLD"
    soft_depend = ["inventoryui", "blockdata_api"]

    commands = {
        "backpack": {
            "description": "Main command for NinjOSBackpacks",
            "usages": [
                "/backpack",
                "/backpack assign [player: player] [tier: str] [extra_lore: message]",
                "/backpack config",
                "/backpack open [player_name: str] [tier: str]",
                "/backpack delete [player_name: str] [tier: str]",
                "/backpack info",
                "/backpack reload",
                "/backpack list",
                "/backpack cleanup"
            ],
            "permissions": ["ninjosbackpacks.command"]
        },
        "hopper": {
            "description": "Control Advanced Hoppers",
            "usages": [
                "/hopper",
                "/hopper info",
                "/hopper link",
                "/hopper unlink",
                "/hopper reload",
                "/hopper list",
                "/hopper debug [state: str]"
            ],
            "permissions": ["ninjoshopper.use"]
        },
        "manageinv": {
            "description": "Open inventory management interface",
            "usages": ["/manageinv"],
            "permissions": ["ninjosbackpacks.admin.inv"]
        }
    }

    permissions = {
        "ninjosbackpacks.command": {
            "description": "Allow using base backpack command",
            "default": "true"
        },
        "ninjosbackpacks.command.give": {
            "description": "Allow giving backpacks to players",
            "default": "op"
        },
        "ninjosbackpacks.command.open": {
            "description": "Allow opening any backpack by player name",
            "default": "op"
        },
        "ninjosbackpacks.command.delete": {
            "description": "Allow deleting a player's backpack",
            "default": "op"
        },
        "ninjosbackpacks.command.info": {
            "description": "Allow checking information of a backpack",
            "default": "true"
        },
        "ninjosbackpacks.command.reload": {
            "description": "Allow reloading the configuration file",
            "default": "op"
        },
        "ninjosbackpacks.command.list": {
            "description": "Allow listing all registered backpacks in the database",
            "default": "op"
        },
        "ninjosbackpacks.admin.bypass": {
            "description": "Allow bypassing ownership restrictions to open backpacks",
            "default": "op"
        },
        "ninjoshopper.use": {
            "description": "Allow using basic hopper commands",
            "default": "true"
        },
        "ninjoshopper.link": {
            "description": "Allow linking hoppers",
            "default": "true"
        },
        "ninjoshopper.unlink": {
            "description": "Allow unlinking hoppers",
            "default": "true"
        },
        "ninjoshopper.admin": {
            "description": "Allow administrative hopper commands",
            "default": "op"
        },
        "ninjosbackpacks.admin.inv": {
            "description": "Allow using the inventory/enderchest manager",
            "default": "op"
        }
    }

    def on_load(self) -> None:
        self.logger.info("NinjOSBackpacks loading...")
        
        # Save and load configuration
        self.save_default_config()
        self.cfg = Config(self)

        # Setup SQLite/MySQL Database
        db_path = self.data_folder / "backpacks.db"
        self.db = Database(db_path, self.logger, self.cfg.mysql)

        # Synchronize database sizes with current config definitions
        try:
            tier_sizes = {}
            for k, v in self.cfg.item_backpacks.items():
                tier_sizes[k] = v.get("size", 27)
            for k, v in self.cfg.block_storage.items():
                tier_sizes[k] = v.get("size", 27)
            
            self.db.update_backpack_sizes(tier_sizes)
        except Exception as e:
            self.logger.error(f"Failed to synchronize backpack sizes: {e}")

        # Initialize Backpack Manager
        self.manager = BackpackManager(self)

        # Initialize Command Handler
        self.cmd_handler = CommandHandler(self)

        # Initialize Inventory Manager UI
        self.inv_manager_ui = InventoryManagerUI(self)

        # Initialize Advanced Hopper module
        from ninjos_backpacks.advanced_hopper import AdvancedHopperModule
        self.hopper_module = AdvancedHopperModule(self)

    def on_enable(self) -> None:
        # Register events
        self.register_events(self)
        self.register_events(self.hopper_module.manager)
        
        # Start the recurring scanner scheduler loop
        self.hopper_module.start()
        
        # Monkey patch EventListener._handle_ping to handle timestamp scaling mismatches in BDS/client handshakes
        self.logger.info("Applying runtime monkey-patch to endstone-inventoryui EventListener...")
        try:
            import endstone_inventoryui.listener
            from bedrock_protocol.packets.packet import NetworkStackLatencyPacket
            from endstone_inventoryui.manager.player_manager import find_session
            from endstone_inventoryui.manager import Session

            def patched_handle_ping(listener_inst, player, payload: bytes) -> None:
                session = find_session(player)
                if session is None:
                    return

                pk = NetworkStackLatencyPacket()
                pk.deserialize(payload)
                
                # Check for timestamp scaling mismatches (BDS vs Client raw timestamps)
                matched = False
                if session.ack_timestamp == pk.timestamp:
                    matched = True
                elif session.ack_timestamp // 1_000_000 == pk.timestamp:
                    matched = True
                elif session.ack_timestamp // 1_000 == pk.timestamp:
                    matched = True
                elif pk.timestamp // 1_000_000 == session.ack_timestamp:
                    matched = True
                elif pk.timestamp // 1_000 == session.ack_timestamp:
                    matched = True
                
                # Fallback to absolute proximity check (within 5 seconds tolerance)
                if not matched:
                    if abs((session.ack_timestamp // 1_000_000) - pk.timestamp) < 5:
                        matched = True
                    elif abs(session.ack_timestamp - pk.timestamp) < 5000000:
                        matched = True

                if not matched:
                    listener_inst._plugin.logger.info(
                        f"[InventoryUI Patched] Timestamp mismatch: expected {session.ack_timestamp}, got {pk.timestamp}. Discarding ping."
                    )
                    return

                listener_inst._plugin.logger.info(
                    f"[InventoryUI Patched] Handshake ping matched! state={session.state}, timestamp={pk.timestamp}"
                )

                match session.state:
                    case Session.State.GRAPHIC_SENT:
                        session.update_state(Session.State.GRAPHIC_RECEIVED)
                    case Session.State.GRAPHIC_DATA_SENT:
                        session.update_state(Session.State.GRAPHIC_DATA_RECEIVED)
                    case Session.State.OPENING:
                        if session.open_attempts >= Session.MAX_OPEN_ATTEMPTS:
                            session.close()
                            return
                        session.open_attempts += 1
                        session.open()

            endstone_inventoryui.listener.EventListener._handle_ping = patched_handle_ping
            self.logger.info("Successfully monkey-patched InventoryUI EventListener class!")
        except Exception as patch_err:
            self.logger.error(f"Failed to monkey-patch InventoryUI EventListener: {patch_err}")

        # Unconditionally register InventoryUI EventListener manually to ensure it runs
        # under the API 0.11 context (preventing packet intercept drops due to InventoryUI's legacy api_version = "0.6").
        self.logger.info("Registering InventoryUI EventListener manually under 0.11 context...")
        try:
            from endstone_inventoryui.listener import EventListener as UIListener
            self.register_events(UIListener(self))
            self.logger.info("Successfully registered InventoryUI event listeners!")
        except Exception as e:
            self.logger.error(f"Failed to manually register InventoryUI event listeners: {e}")
                
        self.logger.info("NinjOSBackpacks successfully enabled!")

    def on_disable(self) -> None:
        self.logger.info("NinjOSBackpacks disabling...")
        # Clean up active sessions
        self.manager.active_item_sessions.clear()
        self.logger.info("NinjOSBackpacks successfully disabled.")

    def on_command(self, sender: CommandSender, command: Command, args: List[str]) -> bool:
        if command.name == "backpack":
            return self.cmd_handler.execute(sender, command, args)
        if command.name == "hopper":
            return self.hopper_module.commands.on_command(sender, command, args)
        if command.name == "manageinv":
            if not isinstance(sender, Player):
                sender.send_message(ColorFormat.RED + "This command can only be run by a player.")
                return True
            self.inv_manager_ui.open(sender)
            return True
        return False

    # ==========================================
    # EVENT HANDLERS
    # ==========================================

    @event_handler
    def on_player_interact(self, event: PlayerInteractEvent) -> None:
        """Handle interactions with placed block-based storage vaults and held backpack items."""
        try:
            player = event.player
            if not player:
                return

            # Bypass if in hopper linking mode
            if str(player.unique_id) in self.hopper_module.manager.linking_states:
                return

            # Check if player already has an active inventory UI session open
            try:
                from endstone_inventoryui.manager.player_manager import find_session as find_ui_session
                if find_ui_session(player):
                    return
            except Exception:
                pass

            action = event.action
            block = event.block

            # 1. Check if they clicked a block vault
            if block and action == PlayerInteractEvent.Action.RIGHT_CLICK_BLOCK:
                norm_clicked_type = normalize_block_type(str(block.type))
                matched_block_tier = None
                for tier, settings in self.cfg.block_storage.items():
                    norm_config_type = normalize_block_type(settings.get("block_type", ""))
                    if settings.get("enabled", True) and norm_config_type == norm_clicked_type:
                        matched_block_tier = tier
                        break

                if matched_block_tier:
                    event.is_cancelled = True
                    self.manager.open_block_storage(player, block.location, matched_block_tier)
                    return

            # 2. Check if they are holding an item-based backpack
            if action == PlayerInteractEvent.Action.RIGHT_CLICK_AIR or action == PlayerInteractEvent.Action.RIGHT_CLICK_BLOCK:
                held_slot = player.inventory.held_item_slot
                held_item = player.inventory.get_item(held_slot)
                backpack_id = get_backpack_id_from_item(held_item)
                if backpack_id:
                    event.is_cancelled = True
                    
                    # Match item material to configuration
                    norm_held = normalize_block_type(str(held_item.type))
                    matched_tier = None
                    for tier, bp in self.cfg.item_backpacks.items():
                        norm_material = normalize_block_type(bp.get("material", ""))
                        if bp.get("enabled", True) and norm_material == norm_held:
                            matched_tier = tier
                            break
                    
                    if matched_tier:
                        self.manager.open_item_backpack(player, backpack_id, matched_tier, held_item)
                    else:
                        player.send_message(f"{ColorFormat.RED}This item material is not configured as a backpack.")
                    return
        except Exception as e:
            self.logger.error(f"[Backpack ERROR] Exception in on_player_interact: {e}\n{traceback.format_exc()}")

    @event_handler
    def on_block_place(self, event: BlockPlaceEvent) -> None:
        """Register newly placed block vaults and block backpack placement."""
        try:
            player = event.player
            if not player:
                return

            placed_block = event.block
            if hasattr(event, 'block_placed_state') and event.block_placed_state:
                placed_block = event.block_placed_state

            if not placed_block:
                return

            # Prevent placing item-backpacks as physical blocks
            held_slot = player.inventory.held_item_slot
            held_item = player.inventory.get_item(held_slot)
            if get_backpack_id_from_item(held_item) is not None:
                player.send_message(f"{ColorFormat.RED}You cannot place backpack items on the ground!")
                event.is_cancelled = True
                return

            # Register placed block vault
            norm_placed_type = normalize_block_type(str(placed_block.type))
            matched_block_tier = None
            for tier, settings in self.cfg.block_storage.items():
                norm_config_type = normalize_block_type(settings.get("block_type", ""))
                if settings.get("enabled", True) and norm_config_type == norm_placed_type:
                    matched_block_tier = tier
                    break

            if matched_block_tier:
                block_key = f"block:{placed_block.location.dimension.name}:{int(placed_block.location.x)}:{int(placed_block.location.y)}:{int(placed_block.location.z)}"
                size = self.cfg.block_storage[matched_block_tier].get("size", 27)
                self.db.save_item_backpack(block_key, matched_block_tier, size, str(player.unique_id), player.name, {})
                player.send_message(f"{ColorFormat.GREEN}Placed {self.cfg.block_storage[matched_block_tier].get('display_name')} successfully.")
        except Exception as e:
            self.logger.error(f"[Backpack ERROR] Exception in on_block_place: {e}\n{traceback.format_exc()}")

    @event_handler
    def on_block_break(self, event: BlockBreakEvent) -> None:
        """Handle block-based storage breakages. Drop contents and verify ownership."""
        try:
            player = event.player
            if not player:
                return

            block = event.block
            if not block:
                return

            norm_broken_type = normalize_block_type(str(block.type))
            matched_block_tier = None
            for tier, settings in self.cfg.block_storage.items():
                norm_config_type = normalize_block_type(settings.get("block_type", ""))
                if settings.get("enabled", True) and norm_config_type == norm_broken_type:
                    matched_block_tier = tier
                    break

            if matched_block_tier:
                block_key = f"block:{block.location.dimension.name}:{int(block.location.x)}:{int(block.location.y)}:{int(block.location.z)}"
                
                # 1. Prevent break if the vault is currently open by anyone
                if block_key in self.manager.active_item_sessions:
                    player.send_message(f"{ColorFormat.RED}You cannot break this vault while it is being used!")
                    event.is_cancelled = True
                    return

                # 2. Check ownership: Only the placer (owner) or an OP admin can break it
                data = self.db.get_item_backpack(block_key)
                if data:
                    owner_uuid = data.get("owner_uuid")
                    owner_name = data.get("owner_name")
                    if owner_uuid and owner_uuid != str(player.unique_id) and not player.is_op:
                        player.send_message(f"{ColorFormat.RED}You do not own this block vault! Only the placer ({owner_name}) can break it.")
                        event.is_cancelled = True
                        return

                    # 3. Retrieve stored items and drop them in the world
                    contents = data.get("contents", {})
                    from ninjos_backpacks.serializer import deserialize_item
                    
                    dropped_count = 0
                    for slot_str, item_data in contents.items():
                        if item_data:
                             try:
                                 item = deserialize_item(item_data)
                                 if item and str(item.type) != "minecraft:air":
                                     block.location.dimension.drop_item(block.location, item)
                                     dropped_count += 1
                             except Exception as de:
                                 self.logger.error(f"Failed to deserialize item drop during break: {de}")

                    # 4. Clean up DB record
                    self.db.delete_item_backpack(block_key)
                    
                    if dropped_count > 0:
                        player.send_message(f"{ColorFormat.YELLOW}Block vault broken. {dropped_count} items spilled.")
                    else:
                        player.send_message(f"{ColorFormat.YELLOW}Block vault broken.")
        except Exception as e:
            self.logger.error(f"[Backpack ERROR] Exception in on_block_break: {e}\n{traceback.format_exc()}")

    @event_handler
    def on_player_join(self, event: PlayerJoinEvent) -> None:
        """Handle player join - save user info to database"""
        try:
            player = event.player
            if player:
                join_time = int(time.time())
                self.db.save_user(player, join_time)
        except Exception as e:
            self.logger.error(f"Failed to save user info on join: {e}")

    @event_handler
    def on_player_quit(self, event: PlayerQuitEvent) -> None:
        """Flush active locks and save player data on quit."""
        player = event.player
        if player:
            # Clear backpack sessions/locks
            self.manager.clear_player_sessions(str(player.unique_id))
            
            # Save user leave time, inventory and ender chest info
            try:
                leave_time = int(time.time())
                self.db.update_user_leave_time(player.xuid, leave_time)
                self.db.save_inventory(player)
                self.db.save_enderchest(player)
            except Exception as e:
                self.logger.error(f"Failed to save player inventory data on quit: {e}")
