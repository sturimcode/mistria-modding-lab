"""mistria-modding-lab: test Fields of Mistria mods in a separate copy of the game."""
from .config import Config, LabStop, load
from .lab import Lab

__version__ = '0.1.0'
__all__ = ['Config', 'Lab', 'LabStop', 'load', '__version__']
