"""Registro de fuentes verificadas; agregar aquí los próximos adaptadores."""

from .avantix import AdaptadorAvantix
from .brega import AdaptadorBrega
from .gaggiotti import AdaptadorGaggiotti

FUENTES = {
    "avantix": AdaptadorAvantix,
    "brega": AdaptadorBrega,
    "gaggiotti": AdaptadorGaggiotti,
}
