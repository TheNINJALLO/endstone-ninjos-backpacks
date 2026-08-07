from ninjos_backpacks.advanced_hopper.hopper_manager import HopperManager
from ninjos_backpacks.advanced_hopper.hopper_scanner import HopperScanner
from ninjos_backpacks.advanced_hopper.hopper_commands import HopperCommands

class AdvancedHopperModule:
    def __init__(self, plugin):
        self.plugin = plugin
        self.manager = HopperManager(plugin)
        self.scanner = HopperScanner(self.manager)
        self.commands = HopperCommands(self.manager)
        
    def start(self) -> None:
        # Schedule the staggered scan task recursively on every single tick
        def run_staggered_ticks():
            try:
                self.scanner.tick()
            except Exception as e:
                self.plugin.logger.error(f"Error in hopper tick loop: {e}")
            self.plugin.server.scheduler.run_task(self.plugin, run_staggered_ticks, delay=1)

        self.run_task_ref = run_staggered_ticks
        self.plugin.server.scheduler.run_task(self.plugin, run_staggered_ticks, delay=20)
        self.plugin.logger.info("Advanced Hopper Module Scheduler loop started.")
