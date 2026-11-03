"""Compatibility imports for the original Infantry movement API."""
from apps.combat.mobile import (
    crowd_offset,
    display_position,
    initialize_infantry_spawn,
)
from apps.combat.mobile import (
    move_mobile_units as move_infantry,
)

__all__ = ["crowd_offset", "display_position", "initialize_infantry_spawn", "move_infantry"]
