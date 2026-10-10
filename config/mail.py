"""El proyecto no tiene una funcionalidad de envío de correo en producción."""

from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend


class CorreoDeshabilitado(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        raise ImproperlyConfigured(
            "El envío de correo está deshabilitado. Configurar un proveedor "
            "en MAILERS antes de incorporar funcionalidades de correo."
        )
