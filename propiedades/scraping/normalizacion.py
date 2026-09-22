import re
from decimal import Decimal, InvalidOperation

def normalizar_precio(precio_crudo):
    if not precio_crudo:
        return None, ""

    #strip limpia espacios, upper cambia minusculas por mausculas usd -> USD
    texto = precio_crudo.strip().upper()

    if texto.startswith("USD"):
        moneda = "USD"
    elif texto.startswith("ARS") or texto.startswith("$"):
        moneda = "ARS"
    else:
        return None, ""

    #re.sub reemplaza las partes que coinicden con un patron
    #elimina todo excepto numero, puntos y comas
    numero_texto = re.sub(r"[^\d,.]", "", texto)
    numero_texto = numero_texto.replace(".", "").replace(",",".")

    try: 
        precio = Decimal(numero_texto)
    except InvalidOperation:
        return None, moneda
    return precio, moneda

def normalizar_tipo(descripcion):
    if not descripcion:
        return ""
    tipo, separador, _ = descripcion.partition(" en ")

    if not separador:
        return descripcion.strip()

    return tipo.strip()

def normalizar_operaciones(descripcion):
    if not descripcion:
        return False, False

    texto = " ".join(descripcion.lower().split())

    en_venta= "venta" in texto
    en_alquiler = "alquiler" in texto

    return en_venta, en_alquiler