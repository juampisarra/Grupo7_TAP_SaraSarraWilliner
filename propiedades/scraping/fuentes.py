"""Registro de fuentes verificadas; agregar aquí los próximos adaptadores."""

from .avantix import AdaptadorAvantix
from .brega import AdaptadorBrega

FUENTES = {
    "avantix": AdaptadorAvantix,
    "brega": AdaptadorBrega,
}
