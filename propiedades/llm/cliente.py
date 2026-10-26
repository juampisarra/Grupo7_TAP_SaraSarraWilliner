"""REST de Gemini aislada, con errores públicos sin secretos ni respuesta cruda."""

import json
import re

from django.conf import settings
import requests

from .prompts import INSTRUCCIONES, esquema_respuesta


class LLMNoDisponible(Exception):
    def __init__(self, mensaje, *, status=503, codigo="ia_no_disponible"):
        super().__init__(mensaje)
        self.status = status
        self.codigo = codigo


def configurado():
    return bool(settings.GEMINI_API_KEY and re.fullmatch(r"[a-zA-Z0-9._-]{1,120}", settings.GEMINI_MODEL))


def validar_respuesta(datos, ids):
    def texto(valor):
        return isinstance(valor, str) and 0 < len(valor.strip()) <= 2500

    def lista(valor):
        return isinstance(valor, list) and len(valor) <= 8 and all(texto(v) for v in valor)

    campos = {"resumen", "diferencias", "por_propiedad", "datos_faltantes", "conclusion"}
    valido = isinstance(datos, dict) and set(datos) == campos
    if valido:
        valido = (texto(datos["resumen"]) and texto(datos["conclusion"])
                  and lista(datos["diferencias"]) and lista(datos["datos_faltantes"])
                  and isinstance(datos["por_propiedad"], list)
                  and len(datos["por_propiedad"]) == len(ids))
    encontrados = []
    if valido:
        for p in datos["por_propiedad"]:
            if not (isinstance(p, dict) and set(p) == {"propiedad_id", "ventajas", "limitaciones"}
                    and type(p["propiedad_id"]) is int and lista(p["ventajas"]) and lista(p["limitaciones"])):
                valido = False
                break
            encontrados.append(p["propiedad_id"])
        valido = valido and sorted(encontrados) == sorted(ids)
    if not valido or len(json.dumps(datos, ensure_ascii=False)) > 14000:
        raise LLMNoDisponible("La IA devolvió un análisis incompleto o inválido. Podés reintentar.",
                              codigo="respuesta_ia_invalida")
    return datos


def generar_analisis(datos):
    if not configurado():
        raise LLMNoDisponible("El análisis con IA todavía no está configurado. Podés usar la tabla comparativa.")
    ids = [p["id"] for p in datos["propiedades"]]
    payload = {
        "systemInstruction": {"parts": [{"text": INSTRUCCIONES}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(datos, ensure_ascii=False)}]}],
        "generationConfig": {
            "temperature": 0.2, "maxOutputTokens": 3000,
            "responseMimeType": "application/json", "responseJsonSchema": esquema_respuesta(ids),
        },
    }
    try:
        respuesta = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": settings.GEMINI_API_KEY}, json=payload,
            timeout=(3, settings.GEMINI_TIMEOUT), allow_redirects=False,
        )
    except requests.RequestException:
        raise LLMNoDisponible("La IA no respondió a tiempo. La tabla sigue disponible; podés reintentar.") from None
    if respuesta.status_code == 429:
        raise LLMNoDisponible("Se alcanzó el límite del proveedor de IA. Intentá más tarde.",
                              status=429, codigo="cuota_ia_agotada")
    if respuesta.status_code != 200:
        raise LLMNoDisponible("No se pudo obtener el análisis con IA. Intentá más tarde.")
    try:
        cuerpo = respuesta.json()
        candidato = cuerpo["candidates"][0]
        if candidato.get("finishReason") != "STOP":
            raise ValueError("Respuesta no completa")
        partes = candidato["content"]["parts"]
        contenido = "".join(p.get("text", "") for p in partes if not p.get("thought"))
        if len(contenido) > 14000:
            raise ValueError("Respuesta demasiado larga")
        resultado = json.loads(contenido)
    except (ValueError, KeyError, IndexError, TypeError, AttributeError, RecursionError):
        raise LLMNoDisponible("La IA no devolvió un análisis utilizable. Podés reintentar.",
                              codigo="respuesta_ia_invalida") from None
    return validar_respuesta(resultado, ids)
