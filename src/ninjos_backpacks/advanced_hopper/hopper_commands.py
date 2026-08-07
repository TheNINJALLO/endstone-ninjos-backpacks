import math
from typing import List, Optional

from endstone import Player, ColorFormat
from endstone.command import Command, CommandSender

class HopperCommands:
    def __init__(self, manager):
        self.manager = manager
        self.logger = manager.logger

    def get_closest_hopper(self, player: Player) -> Optional[dict]:
        px, py, pz = player.location.x, player.location.y, player.location.z
        dim = player.location.dimension.name
        
        closest = None
        min_dist = 6.0
        
        for hopper in self.manager.db.list_hoppers():
            parts = hopper["hopper_key"].split(":")
            if len(parts) >= 5 and parts[1] == dim:
                try:
                    hx, hy, hz = int(parts[2]), int(parts[3]), int(parts[4])
                    dist = math.sqrt((px - hx)**2 + (py - hy)**2 + (pz - hz)**2)
                    if dist < min_dist:
                        min_dist = dist
                        closest = hopper
                except ValueError:
                    continue
        return closest

    def on_command(self, sender: CommandSender, command: Command, args: List[str]) -> bool:
        if not isinstance(sender, Player):
            sender.send_message(f"{ColorFormat.RED}This command can only be used by players in-game.")
            return True

        player = sender
        player_uuid = str(player.unique_id)
        
        subcommand = args[0].lower() if len(args) > 0 else ""

        if not subcommand or subcommand == "info":
            # Show info of closest hopper
            hopper = self.get_closest_hopper(player)
            if not hopper:
                player.send_message(f"{ColorFormat.RED}No advanced hopper found nearby (within 6 blocks).")
                return True
            
            parts = hopper["hopper_key"].split(":")
            owner_name = hopper.get("owner_name", "Unknown")
            enabled = "Enabled" if hopper.get("enabled", True) else "Disabled"
            mode = hopper.get("mode", "whitelist").capitalize()
            hr = hopper.get("horizontal_range", 8)
            vu = hopper.get("vertical_up", 4)
            vd = hopper.get("vertical_down", 4)
            
            link = hopper.get("linked_storage")
            if link:
                link_desc = f"{link.get('dimension')} {link.get('x')} {link.get('y')} {link.get('z')}"
                link_status = "Valid" if self.manager.adapter.is_valid_storage(link.get("storage_id")) else "Invalid Target"
            else:
                link_desc = "None"
                link_status = "Unlinked"
                
            stats = hopper.get("stats", {})
            moved = stats.get("items_moved_total", 0)
            
            player.send_message(f"{ColorFormat.GOLD}=== Advanced Hopper Info ===")
            player.send_message(f" {ColorFormat.YELLOW}Location: {ColorFormat.WHITE}{parts[2]}, {parts[3]}, {parts[4]} ({parts[1]})")
            player.send_message(f" {ColorFormat.YELLOW}Owner: {ColorFormat.WHITE}{owner_name}")
            player.send_message(f" {ColorFormat.YELLOW}Status: {ColorFormat.WHITE}{enabled}")
            player.send_message(f" {ColorFormat.YELLOW}Filter Mode: {ColorFormat.WHITE}{mode}")
            player.send_message(f" {ColorFormat.YELLOW}Range: {ColorFormat.WHITE}{hr} horiz, {vu} up, {vd} down")
            player.send_message(f" {ColorFormat.YELLOW}Linked Storage: {ColorFormat.WHITE}{link_desc} ({link_status})")
            player.send_message(f" {ColorFormat.YELLOW}Items Moved Total: {ColorFormat.WHITE}{moved:,}")
            player.send_message(f" {ColorFormat.YELLOW}Last Scan Status: {ColorFormat.WHITE}{stats.get('last_status', 'None')}")
            return True

        if subcommand == "link":
            if not player.has_permission("ninjoshopper.link"):
                player.send_message(f"{ColorFormat.RED}You do not have permission to link hoppers.")
                return True

            self.manager.linking_states[player_uuid] = {"source_hopper": None}
            player.send_message(f"{ColorFormat.GOLD}Linking Mode Enabled! Right-click the Advanced Hopper block you want to configure.")
            return True

        if subcommand == "unlink":
            if not player.has_permission("ninjoshopper.unlink"):
                player.send_message(f"{ColorFormat.RED}You do not have permission to unlink hoppers.")
                return True

            hopper = self.get_closest_hopper(player)
            if not hopper:
                player.send_message(f"{ColorFormat.RED}No advanced hopper found nearby (within 6 blocks).")
                return True

            if self.manager.cfg.ownership_enabled and hopper.get("owner_uuid") != player_uuid and not player.is_op:
                player.send_message(f"{ColorFormat.RED}You do not own this hopper.")
                return True

            hopper["linked_storage"] = None
            if "storage_full" in hopper.get("stats", {}):
                hopper["stats"]["storage_full"] = False
            
            self.manager.db.save_hopper(hopper["hopper_key"], hopper)
            player.send_message(f"{ColorFormat.GREEN}✓ Hopper at {hopper['hopper_key'].split(':')[2]}, {hopper['hopper_key'].split(':')[3]}, {hopper['hopper_key'].split(':')[4]} successfully unlinked.")
            return True

        if subcommand == "reload":
            if not player.has_permission("ninjoshopper.admin"):
                player.send_message(f"{ColorFormat.RED}You do not have permission to reload hopper configurations.")
                return True

            self.manager.cfg.load()
            player.send_message(f"{ColorFormat.GREEN}✓ Advanced Hopper configuration reloaded.")
            return True

        if subcommand == "list":
            if not player.has_permission("ninjoshopper.admin"):
                player.send_message(f"{ColorFormat.RED}You do not have permission to list hoppers.")
                return True

            hoppers = self.manager.db.list_hoppers()
            player.send_message(f"{ColorFormat.GOLD}=== Advanced Hoppers Registered ({len(hoppers)}) ===")
            for h in hoppers[:15]:
                parts = h["hopper_key"].split(":")
                linked = "Linked" if h.get("linked_storage") else "Unlinked"
                player.send_message(f" {ColorFormat.GRAY}- {parts[2]}, {parts[3]}, {parts[4]} | Owner: {h.get('owner_name')} | Status: {linked}")
            return True

        if subcommand == "debug":
            if not player.has_permission("ninjoshopper.admin"):
                player.send_message(f"{ColorFormat.RED}You do not have permission to use debug commands.")
                return True

            if len(args) < 2:
                player.send_message(f"{ColorFormat.RED}Usage: /hopper debug <on|off>")
                return True

            state = args[1].lower()
            if state == "on":
                self.manager.cfg.debug_timing = True
                player.send_message(f"{ColorFormat.GREEN}✓ Hopper scan debug timing enabled.")
            else:
                self.manager.cfg.debug_timing = False
                player.send_message(f"{ColorFormat.GREEN}✓ Hopper scan debug timing disabled.")
            return True

        player.send_message(f"{ColorFormat.RED}Unknown subcommand. Available: info, link, unlink, list, reload, debug")
        return True
