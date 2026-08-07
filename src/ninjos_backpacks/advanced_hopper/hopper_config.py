from typing import Dict, Any, List

class HopperConfig:
    def __init__(self, parent_cfg):
        self.parent_cfg = parent_cfg
        self.enabled: bool = True
        self.block_id: str = "ninjos:hopper"
        
        # Default hopper settings
        self.default_enabled: bool = True
        self.default_mode: str = "blacklist"
        self.default_horizontal_range: int = 8
        self.default_vertical_up: int = 4
        self.default_vertical_down: int = 4
        self.default_max_items_moved: int = 8
        self.default_max_stacks_moved: int = 3

        # Range boundaries
        self.allowed_horizontal: List[int] = [4, 8, 16, 32]
        self.allowed_vertical: List[int] = [1, 2, 4, 8, 16]
        self.max_horizontal: int = 32
        self.max_vertical_up: int = 16
        self.max_vertical_down: int = 16

        # Movement rules
        self.scan_interval_ticks: int = 20
        self.max_items_moved_per_scan: int = 8
        self.max_stacks_moved_per_scan: int = 3
        self.merge_partial_stacks: bool = True
        self.respect_destination_capacity: bool = True
        self.drop_overflow: bool = False

        # Performance settings
        self.max_hoppers_processed_per_tick: int = 25
        self.max_entity_checks_per_hopper: int = 100
        self.skip_unloaded_chunks: bool = True
        self.require_chunk_loaded: bool = True
        self.pause_when_no_players_nearby: bool = True
        self.player_nearby_range: float = 64.0
        self.debug_timing: bool = False

        # Safety rules
        self.max_hoppers_per_chunk: int = 16
        self.max_hoppers_per_player: int = 100
        self.max_horizontal_range_without_permission: int = 16
        self.max_vertical_range_without_permission: int = 8
        self.require_permission_for_large_range: bool = True
        self.disable_hopper_when_storage_full: bool = False
        self.storage_full_cooldown_ticks: int = 100

        # Filtering traits
        self.match_type: bool = True
        self.match_name: bool = False
        self.match_lore: bool = False
        self.match_enchants: bool = False
        self.match_damage: bool = False
        self.match_custom_data: bool = True

        # Linking
        self.require_manual_link: bool = True
        self.auto_link_adjacent_container: bool = False
        self.allow_unlinked_collection: bool = False
        self.allow_internal_buffer: bool = False
        self.require_same_dimension: bool = True
        self.max_link_distance: float = 8.0
        self.owner_must_have_access_to_storage: bool = True
        self.prevent_linking_to_other_players_storage: bool = True
        self.admin_bypass_link_distance: bool = True

        # Ownership
        self.ownership_enabled: bool = True
        self.owner_only_config: bool = True
        self.allow_trusted_players: bool = True
        self.admin_bypass: bool = True

        # Break settings
        self.prevent_break_if_internal_buffer_not_empty: bool = True
        self.drop_internal_buffer_on_break: bool = False
        self.unlink_on_break: bool = True

        self.load()

    def load(self):
        config = self.parent_cfg.plugin.config
        cfg_sect = config.get("advanced_hopper", {})
        if not cfg_sect:
            return

        self.enabled = cfg_sect.get("enabled", self.enabled)
        self.block_id = cfg_sect.get("block_id", self.block_id)

        # Defaults
        defaults = cfg_sect.get("default", {})
        self.default_enabled = defaults.get("enabled", self.default_enabled)
        self.default_mode = defaults.get("mode", self.default_mode)
        self.default_horizontal_range = defaults.get("horizontal_range", self.default_horizontal_range)
        self.default_vertical_up = defaults.get("vertical_up", self.default_vertical_up)
        self.default_vertical_down = defaults.get("vertical_down", self.default_vertical_down)
        self.default_max_items_moved = defaults.get("max_items_moved_per_scan", self.default_max_items_moved)
        self.default_max_stacks_moved = defaults.get("max_stacks_moved_per_scan", self.default_max_stacks_moved)

        # Range limits
        rng = cfg_sect.get("range", {})
        self.allowed_horizontal = rng.get("allowed_horizontal", self.allowed_horizontal)
        self.allowed_vertical = rng.get("allowed_vertical", self.allowed_vertical)
        self.max_horizontal = rng.get("max_horizontal", self.max_horizontal)
        self.max_vertical_up = rng.get("max_vertical_up", self.max_vertical_up)
        self.max_vertical_down = rng.get("max_vertical_down", self.max_vertical_down)

        # Movement rules
        mvt = cfg_sect.get("movement", {})
        self.scan_interval_ticks = mvt.get("scan_interval_ticks", self.scan_interval_ticks)
        self.max_items_moved_per_scan = mvt.get("max_items_moved_per_scan", self.max_items_moved_per_scan)
        self.max_stacks_moved_per_scan = mvt.get("max_stacks_moved_per_scan", self.max_stacks_moved_per_scan)
        self.merge_partial_stacks = mvt.get("merge_partial_stacks", self.merge_partial_stacks)
        self.respect_destination_capacity = mvt.get("respect_destination_capacity", self.respect_destination_capacity)
        self.drop_overflow = mvt.get("drop_overflow", self.drop_overflow)

        # Performance settings
        perf = cfg_sect.get("performance", {})
        self.max_hoppers_processed_per_tick = perf.get("max_hoppers_processed_per_tick", self.max_hoppers_processed_per_tick)
        self.max_entity_checks_per_hopper = perf.get("max_entity_checks_per_hopper", self.max_entity_checks_per_hopper)
        self.skip_unloaded_chunks = perf.get("skip_unloaded_chunks", self.skip_unloaded_chunks)
        self.require_chunk_loaded = perf.get("require_chunk_loaded", self.require_chunk_loaded)
        self.pause_when_no_players_nearby = perf.get("pause_when_no_players_nearby", self.pause_when_no_players_nearby)
        self.player_nearby_range = perf.get("player_nearby_range", self.player_nearby_range)
        self.debug_timing = perf.get("debug_timing", self.debug_timing)

        # Safety rules
        safety = cfg_sect.get("farm_safety", {})
        self.max_hoppers_per_chunk = safety.get("max_hoppers_per_chunk", self.max_hoppers_per_chunk)
        self.max_hoppers_per_player = safety.get("max_hoppers_per_player", self.max_hoppers_per_player)
        self.max_horizontal_range_without_permission = safety.get("max_horizontal_range_without_permission", self.max_horizontal_range_without_permission)
        self.max_vertical_range_without_permission = safety.get("max_vertical_range_without_permission", self.max_vertical_range_without_permission)
        self.require_permission_for_large_range = safety.get("require_permission_for_large_range", self.require_permission_for_large_range)
        self.disable_hopper_when_storage_full = safety.get("disable_hopper_when_storage_full", self.disable_hopper_when_storage_full)
        self.storage_full_cooldown_ticks = safety.get("storage_full_cooldown_ticks", self.storage_full_cooldown_ticks)

        # Filtering traits
        filt = cfg_sect.get("filter_matching", {})
        self.match_type = filt.get("match_type", self.match_type)
        self.match_name = filt.get("match_name", self.match_name)
        self.match_lore = filt.get("match_lore", self.match_lore)
        self.match_enchants = filt.get("match_enchants", self.match_enchants)
        self.match_damage = filt.get("match_damage", self.match_damage)
        self.match_custom_data = filt.get("match_custom_data", self.match_custom_data)

        # Linking
        link = cfg_sect.get("linking", {})
        self.require_manual_link = link.get("require_manual_link", self.require_manual_link)
        self.auto_link_adjacent_container = link.get("auto_link_adjacent_container", self.auto_link_adjacent_container)
        self.allow_unlinked_collection = link.get("allow_unlinked_collection", self.allow_unlinked_collection)
        self.allow_internal_buffer = link.get("allow_internal_buffer", self.allow_internal_buffer)
        self.require_same_dimension = link.get("require_same_dimension", self.require_same_dimension)
        self.max_link_distance = link.get("max_link_distance", self.max_link_distance)
        self.owner_must_have_access_to_storage = link.get("owner_must_have_access_to_storage", self.owner_must_have_access_to_storage)
        self.prevent_linking_to_other_players_storage = link.get("prevent_linking_to_other_players_storage", self.prevent_linking_to_other_players_storage)
        self.admin_bypass_link_distance = link.get("admin_bypass_link_distance", self.admin_bypass_link_distance)

        # Ownership
        owners = cfg_sect.get("ownership", {})
        self.ownership_enabled = owners.get("enabled", self.ownership_enabled)
        self.owner_only_config = owners.get("owner_only_config", self.owner_only_config)
        self.allow_trusted_players = owners.get("allow_trusted_players", self.allow_trusted_players)
        self.admin_bypass = owners.get("admin_bypass", self.admin_bypass)

        # Break settings
        brk = cfg_sect.get("breaking", {})
        self.prevent_break_if_internal_buffer_not_empty = brk.get("prevent_break_if_internal_buffer_not_empty", self.prevent_break_if_internal_buffer_not_empty)
        self.drop_internal_buffer_on_break = brk.get("drop_internal_buffer_on_break", self.drop_internal_buffer_on_break)
        self.unlink_on_break = brk.get("unlink_on_break", self.unlink_on_break)
