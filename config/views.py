from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe


@require_safe
@never_cache
def health(request):
    """Comprueba que Django responde; no verifica bases ni servicios externos."""
    return JsonResponse({"status": "ok"})
