import time
import re
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

geolocalizador = Nominatim(user_agent="Grupo7-TAP/0.1 (proyecto academico)")

def obtener_coordenadas(direccion, ciudad="Rafaela", provincia="Santa Fe"):
    """
    Convierte una dirección de texto en latitud y longitud usando OpenStreetMap.
    Retorna una tupla (latitud, longitud) o (None, None) si falla o no encuentra.
    """
    if not direccion:
        return None, None
        
    dir_limpia = direccion

    # 1. Detectar ciudad correcta ANTES de recortar (las inmobiliarias venden en pueblos vecinos)
    pueblos_vecinos = ["bella italia", "lehmann", "susana", "san cristobal", "san vicente", "san mariano"]
    ciudad_final = ciudad
    dir_lower = dir_limpia.lower()
    for pueblo in pueblos_vecinos:
        if pueblo in dir_lower:
            ciudad_final = pueblo.title()
            break

    # 2. Abreviaturas clásicas y símbolos problemáticos
    reemplazos = {
        "Bv.": "Bulevar", "Av.": "Avenida", "Bv ": "Bulevar ", "Av ": "Avenida ",
        "Almte.": "Almirante", "Almte ": "Almirante ", "Alte.": "Almirante",
        "Gral.": "General", "Gral ": "General ",
        "1ra": "Primera",
        "N°": "", "Nº": ""
    }
    for abrev, completo in reemplazos.items():
        dir_limpia = dir_limpia.replace(abrev, completo)
    
    # 3. Cortar todo lo que esté después de piso, dpto, intersecciones (esq, y) o aclaraciones
    dir_limpia = re.split(r'(?i)\b(piso|dpto|depto|pb|p\.a\.|local|lote|esq\.?|esquina|s/n|s/nº)\b|-|,|\sy\s', dir_limpia)[0].strip()
    
    texto_busqueda = f"{dir_limpia}, {ciudad_final}, {provincia}, Argentina"
    
    try:
        ubicacion = geolocalizador.geocode(texto_busqueda, timeout=10)
        if ubicacion:
            return ubicacion.latitude, ubicacion.longitude
        
        return None, None
        
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        print(f"Error de geocodificación para {direccion}: {e}")
        return None, None
