# Contexto e instrucciones para agentes

Este archivo es el punto de entrada para cualquier agente que trabaje en este repositorio. Leerlo antes de proponer cambios o implementar funcionalidades. Mantenerlo actualizado cuando el equipo confirme nuevas decisiones; no convertir propuestas en decisiones sin confirmación.

## Proyecto

Trabajo práctico de TAP del Grupo 7 (Sara, Sarra y Williner): un buscador y observatorio inmobiliario que centraliza publicaciones de distintas inmobiliarias.

La aplicación obtendrá propiedades mediante scraping de publicaciones públicas, normalizará la información y permitirá buscar, filtrar y comparar opciones desde una sola web, conservando el enlace al aviso original y la inmobiliaria de origen.

El foco inicial es el buscador. Los resúmenes del mercado y análisis históricos son posibles ampliaciones, no requisitos de la primera versión. No se trata de un sistema de gestión de contratos o alquileres.

## Decisiones confirmadas

- Lenguaje: Python.
- Framework web: Django.
- Priorizar una implementación sencilla de entender y mantener, con una web ágil. Explicar las decisiones y los conceptos nuevos de forma clara.
- Empezar con una sola inmobiliaria y completar el recorrido de extracción, normalización, guardado y consulta web.
- Escalar luego a 3 o 4 fuentes para la presentación.
- Reutilizar la extracción mediante adaptadores por plataforma, con configuración por inmobiliaria.

## Funcionamiento esperado

1. Un proceso de extracción consulta las páginas de una inmobiliaria y obtiene los datos disponibles.
2. Normaliza y guarda las publicaciones en una base de datos.
3. Django consulta los datos guardados para responder las búsquedas de los usuarios.

El scraping debe ejecutarse separado de las búsquedas: una visita o un cambio de filtro no debe disparar un recorrido por los sitios externos. El usuario consulta la última información guardada. La frecuencia de actualización queda por definir; al principio se puede ejecutar la extracción manualmente.

Entre los datos de interés están el identificador de la publicación en la fuente, inmobiliaria de origen, dirección o zona, tipo de propiedad, operación, precio y moneda, ambientes, superficie, imagen y URL original. Confirmar qué ofrece cada fuente y representar los datos faltantes sin inventarlos. Mantener diferenciadas las monedas y las unidades para comparar correctamente.

Los filtros iniciales podrán incluir zona, precio, operación (venta o alquiler), tipo de propiedad, ambientes y superficie, según los datos disponibles. Definir el mínimo concreto al implementar la primera versión.

## Fuentes exploradas y reutilización

Se propone comenzar por Brega y sumar Avantix después para probar la reutilización. El orden es la propuesta de trabajo actual, no una restricción técnica.

- Brega: https://www.bregainmobiliaria.ar
- Avantix: https://www.avantix.ar

En la exploración manual conversada, ambos sitios mostraron un patrón compatible con Tokko:

- Propiedades en elementos `li[prop-id]`.
- Clases comunes `.prop-desc-dir` y `.prop-valor-nro`.
- Un primer lote en el HTML inicial y carga adicional al hacer scroll.
- Solicitudes con paginación `p=2`, `p=3`.
- Marcador de fin `--NoMoreProperties--`.

Estos hallazgos provienen de la inspección manual del usuario, no de un scraper ya implementado ni de una verificación automatizada. Verificar las URLs exactas, parámetros, respuesta y selectores antes de programar contra ellos. `p=3` fue un ejemplo observado: no fijar esa página como límite universal.

La hipótesis es compartir un adaptador Tokko entre Brega y Avantix, cambiando la configuración de cada inmobiliaria (nombre, URL base, URL de búsqueda y ajustes necesarios). Confirmar con código cuánto se puede reutilizar. No asumir que todos los sitios Tokko son idénticos.

Después convendría incorporar una fuente de otra plataforma para demostrar la extensión con un adaptador distinto. Esa fuente todavía no está elegida.

## Plan inicial

1. Hacer una prueba pequeña con una página de Brega: extraer dirección, precio y enlace, y revisar el resultado.
2. Recorrer la paginación real con una condición de fin y manejo básico de errores.
3. Guardar los datos normalizados evitando duplicar una publicación de la misma fuente al repetir una carga.
4. Mostrar las propiedades en Django con filtros básicos y acceso al aviso original.
5. Incorporar Avantix y comprobar el adaptador compartido.
6. Ampliar hasta 3 o 4 fuentes para la presentación.

Mantener separadas la extracción, la normalización y las consultas de la web, sin introducir una arquitectura compleja antes de necesitarla. Conservar la procedencia de cada publicación. La detección de una misma propiedad publicada por varias inmobiliarias es un problema distinto de evitar duplicados al repetir una carga; su alcance queda por definir.

## Herramientas propuestas y decisiones pendientes

Python y Django están confirmados. Las siguientes opciones se conversaron, pero todavía no se adoptaron como requisitos:

- Descargar HTML y analizarlo con Beautiful Soup para la primera prueba. Primero comprobar si las consultas directas permiten obtener las publicaciones; no dar por necesaria la automatización de un navegador.
- Usar páginas HTML generadas por Django, con CSS y JavaScript según necesidad, para simplificar la primera versión.
- Desarrollar inicialmente con una base de datos local.

Todavía falta elegir la base de datos definitiva, el alojamiento, la frecuencia de actualización y las fuentes adicionales. Vercel y Supabase se explicaron como alternativas de infraestructura; no se decidió utilizarlos. Tampoco se decidió usar React, una API separada, colas de tareas, microservicios ni un framework de scraping específico.

## Criterios de trabajo

- Revisar el estado real del repositorio antes de asumir qué está implementado. Al registrar este contexto solo estaban el README y este archivo; aún no se había creado la aplicación Django.
- Avanzar por pasos pequeños que el equipo pueda ejecutar y comprender.
- Hacer consultas a las fuentes con tiempos de espera, ritmo moderado y reintentos limitados; evitar bucles de paginación y cargas duplicadas.
- Verificar la extracción con ejemplos reales y distinguir los datos ausentes de los errores de lectura.
- No presentar como funcionalidades existentes las ideas o tareas pendientes de este documento.

## Referencia compartida

Resumen de la idea en el Google Doc «Lluvia de Ideas», pestaña «Idea del TP»:
https://docs.google.com/document/d/1HiQLoD9vaR4fEAyy5bm_5d_fspXELkBCkJn2u0wkB3A/edit?tab=t.xl5s41rt5ksx

Este AGENTS.md contiene el contexto necesario para comenzar sin depender del acceso a la conversación o al documento externo. Las instrucciones explícitas posteriores del equipo prevalecen sobre este contexto.
