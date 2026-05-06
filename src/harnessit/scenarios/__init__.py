"""Eval scenarios shipped with HarnessIT.

Stage 2 ships exactly one: silent-drops localization. Stage 3+ adds
scenarios as the agent grows tool surface to handle them.
"""

from harnessit.scenarios.silent_drops import silent_drops_localization

__all__ = ["silent_drops_localization"]
