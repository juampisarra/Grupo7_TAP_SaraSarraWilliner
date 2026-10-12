"""URLs de imágenes públicas: validación sin descargar archivos ni resolver DNS."""

import ipaddress
from urllib.parse import urljoin, urlsplit, urlunsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator


def normalizar_url_foto(valor, *, url_base=""):
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError("La foto debe tener una URL de texto no vacía")
    valor = valor.strip()
    if any(c.isspace() or ord(c) < 32 for c in valor) or "\\" in valor:
        raise ValueError("URL de foto inválida")
    url = urljoin(url_base, valor)
    try:
        URLValidator(schemes=["https"])(url)
        partes = urlsplit(url)
        host = partes.hostname or ""
        if partes.username is not None or partes.password is not None:
            raise ValueError("Las URLs de fotos no deben incluir credenciales")
        if host.rstrip(".").lower() == "localhost" or host.lower().endswith((".localhost", ".local")):
            raise ValueError("La URL debe ser pública")
        try:
            direccion = ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            if not direccion.is_global:
                raise ValueError("La URL debe ser pública")
    except ValidationError:
        raise ValueError("La foto debe tener una URL HTTPS válida") from None
    # Un fragmento no cambia el recurso; quitarlo también permite deduplicar.
    return urlunsplit((partes.scheme, partes.netloc, partes.path, partes.query, ""))


def normalizar_fotos(valores, *, url_base=""):
    if not isinstance(valores, list):
        raise ValueError("Las fotos deben ser una lista de URLs")
    return list(dict.fromkeys(normalizar_url_foto(v, url_base=url_base) for v in valores))


def validar_fotos(valores):
    """Validador serializable del JSONField, reutilizable desde full_clean."""
    try:
        normalizadas = normalizar_fotos(valores)
    except ValueError as error:
        raise ValidationError(str(error)) from None
    if normalizadas != valores:
        raise ValidationError("Las fotos deben estar normalizadas y sin duplicados")
