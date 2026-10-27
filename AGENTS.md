# Contexto e instrucciones para agentes

Este archivo es el punto de entrada para cualquier agente que trabaje en este repositorio. Leerlo antes de proponer cambios o implementar funcionalidades. Mantenerlo actualizado cuando el equipo confirme nuevas decisiones; no convertir propuestas en decisiones sin confirmación.

## Proyecto y prioridades

Trabajo práctico de TAP del Grupo 7 (Sara, Sarra y Williner): un Observatorio Inmobiliario orientado inicialmente a propiedades de Rafaela. Centraliza publicaciones públicas de distintas inmobiliarias para permitir buscar, filtrar y comparar opciones desde una única aplicación, conservando la inmobiliaria de origen y el enlace al aviso original.

Las tres features principales acordadas son:

1. Ingesta mediante scraping desde múltiples inmobiliarias.
2. Búsqueda de texto completo con Elasticsearch y ranking por relevancia.
3. Búsqueda web con filtros estructurados y geográficos, utilizando exclusivamente PostGIS para la lógica geográfica.

La prioridad es mantener el backend y su integración con el frontend ya incorporado por el equipo. `/propiedades/mapa/` utiliza Django Templates, JavaScript y MapLibre GL JS; `/propiedades/` conserva el listado de prueba. MapTiler es el único proveedor cartográfico del mapa activo y requiere `MAPTILER_API_KEY`. No adoptar otro framework sin una decisión del equipo. Representar honestamente la precisión de las coordenadas.

Los resúmenes del mercado y análisis históricos siguen siendo posibles ampliaciones, no requisitos iniciales. No se trata de un sistema de gestión de contratos o alquileres.

## Stack y responsabilidades confirmadas

| Tecnología | Responsabilidad |
| --- | --- |
| Python | Lenguaje principal para el backend y los jobs de ingesta. |
| Django | Framework del backend ya adoptado e implementado en el repositorio. |
| Supabase / PostgreSQL | Base de datos principal y fuente de verdad: persistencia, información completa de las propiedades y filtros estructurados. |
| PostGIS | Extensión de PostgreSQL responsable de toda la lógica geográfica: coordenadas, distancia, radio, áreas y consultas e índices espaciales. No es una base de datos independiente. |
| Elasticsearch / Elastic Cloud | Elasticsearch es el índice especializado exclusivamente en búsqueda de texto completo y ranking por relevancia; se alojará en Elastic Cloud. No reemplaza PostgreSQL ni realiza filtros geográficos. |
| Render | Django está desplegado y conectado a Supabase y Elastic Cloud. `/propiedades/` permite probar búsqueda textual por relevancia mediante un formulario simple. |
| GitHub Actions | Ejecuta el comando general de ingesta y reconstruye Elasticsearch todos los lunes a las 00:00 de Argentina; también admite ejecución manual. Secrets, concurrencia y primera ejecución están verificados. |
| Frontend | `/propiedades/mapa/` utiliza Django Templates, CSS, JavaScript y MapLibre GL JS, activado por el usuario. Requiere `MAPTILER_API_KEY` para los mapas de MapTiler, con Calles, Oscuro y Satélite. Consulta todas las páginas de la API, coordinando Elasticsearch y PostGIS desde Django. |

Supabase/PostgreSQL, PostGIS y Elasticsearch son decisiones del stack objetivo. La conexión PostgreSQL está implementada mediante psycopg y variables de entorno, y se verificaron independientemente las migraciones hasta `0012` en Supabase el 12 de octubre de 2026; posteriormente el usuario compartió logs productivos de enriquecimiento que utilizan el esquema `0013`, con ocho aplicaciones. No se repitió la auditoría independiente de migraciones después de esos logs. En la revisión del 8 de octubre de 2026 se comprobaron 173 publicaciones, incluyendo datos guardados por el enriquecimiento inverso. No se realizó un traslado automático de SQLite. PostGIS y la búsqueda con Elasticsearch están desplegados. La ingesta programada reconstruye el índice completo después de persistir; la actualización incremental por publicación sigue pendiente. Sin configuración se utiliza SQLite para desarrollo local. Guardar `.env` como UTF-8 sin BOM para que se reconozca correctamente la primera variable.

### Entorno objetivo y despliegue

Entregar un sitio accesible desde una URL pública. Utilizar Django en Render, PostgreSQL y PostGIS en Supabase, Elasticsearch en Elastic Cloud y GitHub Actions para la ingesta automática. Las búsquedas del sitio desplegado funcionan sin depender de una computadora del equipo. Conservar la ejecución local para desarrollo y pruebas. El 11 de octubre de 2026 el equipo confirmó la búsqueda textual pública, el formulario mínimo y una ejecución manual exitosa del workflow completo. PostGIS ya está desplegado. Ver [estado y configuración del despliegue](docs/despliegue.md).

#### Elasticsearch en Elastic Cloud

Utilizar la prueba gratuita de 14 días sin tarjeta para la entrega, comprobando que su vigencia cubra la evaluación antes de activarla. No asumir alojamiento gratuito permanente; la continuidad después de la prueba sigue por resolver. Mantener las credenciales en variables de entorno y conectar Elasticsearch desde el backend y el job, nunca directamente desde el frontend. La creación del servicio, conexión, reconstrucción del índice, búsqueda textual pública y reconstrucción automática posterior a la ingesta están implementadas. El índice puede reconstruirse desde las propiedades guardadas en Supabase. Ver [prueba de Elastic Cloud](https://www.elastic.co/cloud/elasticsearch-service/signup).

#### Ingesta automática con GitHub Actions

El workflow `.github/workflows/ingesta.yml` obtiene el código, instala dependencias, comprueba Elasticsearch, ejecuta `python manage.py importar_propiedades` para todas las fuentes registradas y finalmente ejecuta `python manage.py reconstruir_indice`. Usa Ubuntu 24.04, Python 3.14 y las acciones oficiales basadas en Node 24. Está programado los lunes a las 00:00 de Argentina (`03:00 UTC`) y admite `workflow_dispatch`.

Las credenciales se guardan como Actions Secrets y no en el repositorio. `concurrency` impide dos ejecuciones simultáneas del mismo workflow; también deben evitarse ingestas locales concurrentes contra los mismos servicios. El 11 de octubre de 2026 se verificó una ejecución manual exitosa. Si falla la reconstrucción, PostgreSQL conserva la ingesta y el alias anterior continúa activo; la recuperación actual consiste en corregir la causa y reejecutar el workflow. La recuperación incremental sigue pendiente.

Los runners estándar son gratuitos en repositorios públicos. En repositorios privados, GitHub Free incluye 2.000 minutos mensuales compartidos entre los workflows y repositorios privados de la cuenta propietaria, no por integrante ni por repositorio. Verificar la visibilidad y cuota disponible antes de configurar la programación: el 9 de octubre de 2026 se verificó que este repositorio es público. Ver [facturación de Actions](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

No hace falta contratar un Render Cron Job para esta arquitectura. Esa alternativa tiene un mínimo mensual de USD 1 por servicio, independiente de las solicitudes al servicio web. Ver [Render Cron Jobs](https://render.com/docs/cronjobs).

#### Solicitudes periódicas al servicio web

Preparar solicitudes periódicas desde un servicio externo a una ruta ligera de Django para reducir el reposo por inactividad. Render gratuito entra en reposo tras 15 minutos sin tráfico entrante; los pings no eliminan sus límites ni garantizan disponibilidad continua. Una visita, un filtro o un ping no deben disparar scraping ni indexación. La ruta no debe consultar Supabase o Elasticsearch solo para mantener activo el servicio. Ver [Render Free](https://render.com/docs/free).

La ruta `/health/` está desplegada. El equipo creó el job en [cron-job.org](https://cron-job.org/en/); falta comprobar una ejecución programada HTTP 200 en su historial y el intervalo efectivamente guardado (se propuso GET cada diez minutos). No presentar la creación del job como prueba de ejecución. Vercel fue una opción consultada, no adoptada.

## Estado real del repositorio

### Contraste y desplegables de filtros del lateral — 27 de octubre de 2026

El usuario pidió destacar visualmente el bloque abierto de Filtros y mantener alineados Tipos, Precio/dormitorios y Elegir punto. El lateral usa cabecera azul oscuro, fondo azul claro, borde, sombra y flecha de estado. Los dos menús conservan columnas independientes, alineadas arriba; con hasta 520 px disponibles, Elegir punto pasa a la fila siguiente. Pueden permanecer abiertos al mismo tiempo, incluso al editar precio o activar la selección por punto. Elegir un tipo cierra solo su menú; clic afuera y Escape mantienen el cierre existente. El panel inferior sobre el mapa conserva su comportamiento anterior.

CSS y mapa.js usan `20261027-filtros-paralelos`. Pasaron las 27 pruebas Django de consultas/plantilla con SQLite efímero y almacenamiento de estáticos simple en pruebas, las regresiones Node de mapa y lista (incluida apertura simultánea), sintaxis y `git diff --check`. Sin nueva inspección visual independiente, commit, push ni despliegue. Ver [guía del mapa](docs/mapa.md).

### Comparación de publicaciones y Gemini — 25 de octubre de 2026

El usuario aprobó implementar el plan de selección de entre dos y cuatro publicaciones, tabla comparativa y análisis opcional con Gemini. La selección está integrada en tarjetas de la lista y ficha del mapa, conserva IDs entre búsquedas de la misma operación y se limpia al cambiar entre alquiler/venta. El comparador es un diálogo con tabla obtenida de PostgreSQL, sin depender del LLM. Mantiene datos faltantes, monedas, fuente y precisión; no infiere superficies ni precio/m². No amplía la lista del mapa para incluir avisos sin coordenadas.

Los endpoints nuevos son `/api/propiedades/comparacion/` (GET) y `/api/propiedades/comparacion/analisis/` (POST con CSRF). El servidor recupera los datos por ID y comprueba disponibilidad y firma antes y después del análisis. Gemini utiliza REST con `requests` existente, clave privada y modelo configurables mediante `GEMINI_API_KEY`/`GEMINI_MODEL`, salida JSON validada y datos acotados sin comentarios, direcciones, fotos ni coordenadas. Sin configuración funciona la tabla. No hay modelo predeterminado: verificar disponibilidad, cuota y condiciones de la cuenta en AI Studio antes de activarlo.

La migración nueva `0015_comparaciongenerada_usocomparacion`, dependiente de `0014_comentario`, agrega caché compartida por 24 horas, reservas temporales y contadores atómicos. Límites iniciales: 2 generaciones/minuto/visitante, 5/minuto globales y 100/día UTC; ajustar según cuota real. No se aplicó a Supabase. No se introdujeron dependencias, scraping, indexación ni cambios de propiedades productivas.

Los comentarios **ya existen en el código actual**: modelo `Comentario`, migración `0014`, API, admin e interfaz de ficha. Las notas del 24 de octubre que los describen como pendientes son históricas. No se auditó su publicación ni migración productiva en esta implementación.

Validación: 243 pruebas Django (241 aprobadas y dos integraciones PostGIS omitidas con SQLite), cuatro pruebas Node de comparador/lista/mapa/comentarios, `check`, migraciones pendientes de generar y estáticos correctos. SQLite efímero y proveedor simulado; la prueba real de Gemini sigue pendiente. Computer Use se detuvo al no poder determinar con certeza la URL activa de Chrome; no se continuó la automatización ni se eludió el bloqueo. Revisión visual real de escritorio/celular pendiente. Cambios locales, sin commit, push ni despliegue. Ver [contrato, configuración y pruebas](docs/comparacion.md).

### Panel lateral de resultados del mapa — 24 de octubre de 2026

El equipo pidió avanzar por partes y confirmó como primera etapa únicamente un panel escondible similar al patrón de Airbnb. El panel se abre desde «Ver lista» y muestra solo las propiedades con coordenadas que ya están representadas en el mapa para la búsqueda actual; no realiza otra consulta, no duplica filtros geográficos ni modifica coordenadas. En escritorio desplaza el mapa hacia la derecha y presenta dos columnas de tarjetas; en pantallas de hasta 900 px se superpone, y en celular ocupa todo el ancho. Cerrarlo restaura el mapa y solicita a MapLibre recalcular su tamaño.

El equipo confirmó después que, mientras la lista está abierta, el contenedor inferior no debe permanecer sobre el mapa. La interfaz mueve los controles originales al lateral dentro de un único desplegable compacto, cuyo resumen muestra tipo, dormitorios y comodidades activas. Cerrado ocupa una sola línea; al expandirlo conserva también precio, punto, limpieza y contador. No hay copias de controles ni una segunda lógica de filtros. Al cerrar la lista, el mismo nodo vuelve a su ubicación inferior original.

La lista conserva la operación y los filtros existentes, informa cuántos resultados tienen ubicación, permite filtrar localmente por dirección/tipo/inmobiliaria y ordenar por relevancia cuando hay texto, actualización o precio. Los precios desconocidos quedan al final. Cada tarjeta usa foto, precio, título, ubicación y características básicas; al pulsarla abre la ficha existente y centra su marcador. Los textos del aviso se insertan como texto, no como HTML.

Esta etapa no implementa comparación, Gemini ni comentarios: no agrega modelos, migraciones, endpoints, variables de entorno o dependencias. Pasaron 27 pruebas Django de consultas/plantilla, la regresión Node del mapa y una prueba Node nueva de lista/filtro/orden/apertura/texto seguro, incluyendo el traslado y la restauración del panel de filtros. `check`, migraciones pendientes, sintaxis y estáticos fueron comprobados. La inspección visual independiente quedó bloqueada porque el navegador integrado no puede alcanzar `127.0.0.1` y no había otro navegador controlable; no se intentó eludir esa barrera. Cambios locales, sin commit, push, despliegue ni datos productivos modificados.

### Nuevas features acordadas y trabajo pendiente — 24 de octubre de 2026

El equipo pidió sumar, avanzando de a una feature por vez: vista en lista ordenable y filtrable, selección de varias propiedades para compararlas con sus características y un texto generado por LLM, y comentarios en las publicaciones. La primera etapa es el panel lateral descrito arriba; no comenzar simultáneamente comparación y comentarios sin una indicación nueva del equipo.

Para la presentación, los comentarios serán públicos y no exigirán registro ni autenticación. Esta es una decisión confirmada, pero todavía no hay modelo, migración, API ni interfaz de comentarios en el repositorio. Se conversó como diseño posible asociarlos al ID interno de `Propiedad`, mostrarlos en su ficha y permitir alias opcional con «Anónimo» como respaldo. Los límites de longitud, moderación desde Django Admin y protección contra abuso o frecuencia siguen siendo detalles propuestos: confirmarlos al implementar y conservar CSRF, validación del servidor y renderizado como texto, nunca como HTML.

Para la comparación asistida, el equipo indicó Gemini como proveedor previsto por disponer de nivel gratuito. La comparación y la integración con Gemini siguen sin implementar. Cuando se autorice esa etapa, verificar nuevamente modelos, cuotas y condiciones vigentes; mantener la clave exclusivamente en el backend y en variables de entorno. No enviar al proveedor más datos de los necesarios para comparar las propiedades seleccionadas.

### MapTiler como único proveedor del mapa activo — 13 de octubre de 2026

El equipo confirmó retirar OpenFreeMap. Se eliminaron sus direcciones de estilo/edificios, la selección entre proveedores y las propiedades de altura propias de ese respaldo. MapLibre conserva Streets v4, Streets v4 Dark y Hybrid v4 de MapTiler, logo/atribución y reutilización de Planet v4 para los edificios de Satélite. Se conserva la agrupación, coordenadas, fichas, punto y filtros. Las menciones del respaldo en las etapas anteriores describen el estado histórico, ya reemplazado.

`MAPTILER_API_KEY` es necesaria en `.env` y Environment de Render para mostrar el mapa. Su ausencia detiene únicamente la inicialización del mapa, muestra un mensaje de configuración, deshabilita las vistas y elimina el indicador de carga; no inicia solicitudes a otros proveedores. No exigir esta clave globalmente para iniciar Django, health, API o jobs. Los valores de las claves no se modificaron. CSS/JavaScript usan la versión `20261013-maptiler` para evitar la caché anterior.

Validación: 27 pruebas Django de consultas/plantilla y pruebas Node de las tres vistas, edificios sin duplicación, marcadores/grupos, filtros y error sin clave aprobadas. Sintaxis y estáticos comprobados; SQLite efímero y servicios simulados, sin datos productivos modificados. La inspección visual independiente sigue pendiente por el bloqueo previo del navegador. Cambios locales, sin commit, push ni despliegue. Ver [guía del mapa](docs/mapa.md).

### Tipos disponibles según operación — 13 de octubre de 2026

El equipo confirmó ocultar los tipos sin publicaciones vigentes en la operación elegida. Django obtiene disponibilidad de alquiler/venta de todo el catálogo mediante una sola consulta agrupada en PostgreSQL/SQLite, independiente de paginación, coordenadas y otros filtros. Alquilar empieza con los tipos exclusivos de venta ocultos y deshabilitados. Cambiar de operación actualiza el menú inmediatamente; conserva un tipo disponible en ambas operaciones o limpia uno incompatible a Todos los tipos antes de la única búsqueda. Limpiar conserva la operación y sus opciones. Sin categorías se muestra un mensaje para alquilar o comprar. Recargar actualiza el catálogo tras cambios en la base.

La versión de CSS/JavaScript pasa a `20261013-tipos-operacion` para evitar reutilizar archivos anteriores. Pasaron 27 pruebas Django de consultas/plantilla, pruebas Node de disponibilidad/selección/limpieza y regresiones, sintaxis y estáticos. Pruebas con SQLite efímero y servicios simulados; sin cambios productivos, migraciones, ingesta ni indexación. La inspección visual independiente sigue pendiente por el bloqueo previo de la herramienta del navegador. Cambios locales, sin commit, push ni despliegue. Ver [catálogo por operación](docs/api_propiedades.md#tipos-disponibles-en-el-mapa).

### Selector de vistas en una esquina — 13 de octubre de 2026

El usuario autorizó al agente a terminar los cambios que estaba aplicando manualmente. El selector quedó separado del panel de filtros, en la esquina inferior izquierda del mapa y por encima del logo y la atribución. Usa un botón oscuro con ícono de capas y el nombre de la vista activa: Calles (predeterminada), Oscuro o Satélite. Mantener el selector compacto; Escape y el clic afuera cierran el menú. Estos cambios siguen locales, sin commit, push ni despliegue.

El usuario informó que el selector no aparecía después de reiniciar Django y confirmó que `estilos-menu` sí estaba en el código fuente recibido. Se comprobaron la plantilla efectiva, `DEBUG=True` y las copias actuales de CSS y JavaScript en este proyecto. La plantilla agrega `?v=20261013-vistas` a ambos recursos para solicitar una URL nueva y evitar reutilizar la caché de la versión anterior. Después de recargar con Ctrl+F5, el usuario confirmó que el botón Calles aparece. Pasaron las dos pruebas de plantilla ejecutadas para esta corrección y se verificaron las direcciones versionadas en desarrollo y producción. Esta confirmación del usuario no reemplaza una inspección independiente del cambio entre las tres vistas.

Con clave de MapTiler usa `streets-v4`, `streets-v4-dark` y `hybrid-v4` (imágenes satelitales con etiquetas), conservando cámara, marcadores, ficha, punto y filtros. Las tres configuraciones respondieron HTTP 200 con la clave local y el origen localhost. Calles y Oscuro traen Building 3D de Planet v4; Hybrid no trae edificios. Para Satélite se conserva y reutiliza la definición de la fuente Planet v4 de Calles, del mismo proveedor, agregando una sola capa de extrusión. No cambiar a los estilos de OpenFreeMap para oscurecer el mapa de MapTiler: su cobertura de edificios es distinta. Las alturas de respaldo siguen siendo ilustrativas y no identifican las propiedades.

El controlador valida la respuesta del estilo antes de reemplazar el fondo; ante fallo mantiene la vista y el nombre anteriores, muestra un mensaje y permite reintentar. Las solicitudes tienen cancelación independiente de la búsqueda de propiedades. Sin clave, Calles conserva OpenFreeMap y las otras vistas quedan deshabilitadas. No exige nuevas variables, migraciones, ingesta ni indexación. Pruebas Node verifican las tres vistas, etiqueta activa, cámara/filtros/coordenadas, fuente de edificios satelital sin duplicación, cierre, fallo y ausencia de clave. Pasaron 25 pruebas Django de consultas/plantilla, sintaxis y estáticos. La revisión visual real de este nuevo selector sigue pendiente: la herramienta del navegador rechazó el acceso a la página local y no se intentaron alternativas que eludieran ese bloqueo. Ver [vistas y validación](docs/mapa.md).

El 13 de octubre, por pedido del usuario, se retiró de la ficha del mapa el enlace fijo «Ubicaciones: fuentes originales / OpenStreetMap» y su estilo sin uso. La ficha conserva la inmobiliaria, el aviso original y la precisión de ubicación; el mapa conserva su atribución cartográfica. La mención de OpenStreetMap para ubicaciones geocodificadas sigue dentro del mensaje de precisión.

### Burbujas en columna lateral — 13 de octubre de 2026

Corrección posterior: Bolívar 137 (Gaggiotti/Avantix) tiene coordenadas distintas por fuente y el criterio de igualdad exacta provocaba zoom hasta el máximo y una lista blanca. Ahora también abre la columna si el grupo ocupa como máximo 12 px en cada eje de pantalla. Los grupos más extendidos acercan hasta zoom 18 como máximo automático; si continúan solapados, abren la misma columna. El zoom manual sigue disponible y los puntos distintos pueden separarse al acercar. El texto distingue puntos compartidos de avisos cercanos; este criterio visual no identifica duplicados ni acredita un mismo edificio. Cada ficha conserva fuente, precisión y coordenadas propias. Una prueba reproduce el par real de Bolívar y comprueba apertura sin zoom, selección de ambas fuentes y preservación de ambos registros; también verifica el límite automático y la apertura posterior. Revisión real con filtro Oficina en navegador y celular: dos burbujas directas y ficha Avantix correcta, con fotos, precisión y enlace. Se restauró el tamaño habitual. La búsqueda textual no se verificó en esta ejecución, cuyo proceso local carecía de variables Elasticsearch.

El usuario pidió reemplazar el selector circular por precios apilados al costado del grupo, sin marco ni fondo blanco envolvente. Está implementado localmente: al pulsar un grupo con coordenadas idénticas aparece una columna de botones con emoji y precio, preferentemente a su izquierda; cerca del borde izquierdo abre a la derecha. Se ajusta al espacio entre cabecera y filtros y los grupos grandes admiten desplazamiento vertical. Cada burbuja abre la ficha original. Volver a pulsar el grupo, el botón de cierre, el fondo del mapa, Escape, mover la cámara o cambiar filtros cierra la columna.

El desplazamiento es exclusivamente visual en píxeles, anclado a las coordenadas originales; no cambia datos ni precisión, ni implica que los avisos estén en el mismo edificio. Se mantienen los grupos de puntos distintos que se separan al acercar, MapTiler y el panel compacto. Node verifica selección, cierre, conservación de coordenadas, texto seguro, cambio de lado y grupos de 2/5/8/18 avisos. Sintaxis y estáticos comprobados. Revisión real en el navegador local y en 390×844: cinco burbujas sin marco, selección de Departamento/Gaggiotti con su ficha y cierre al volver a pulsar el grupo. Se restauró el tamaño habitual del navegador. Ver [interfaz y pruebas](docs/mapa.md).

Estos cambios siguen locales; el agente no hizo commit, push ni despliegue. La etapa anterior de diseño está guardada en `e37d837`; las notas circulares que siguen describen la versión reemplazada.

### Diseño original recuperado y selección circular — 13 de octubre de 2026

El usuario confirmó que MapTiler funciona bien y autorizó la siguiente etapa de interfaz. Se recuperaron blanco translúcido, azul, Plus Jakarta Sans y emojis del diseño anterior, manteniendo MapLibre/MapTiler y los filtros inferiores. El panel superior ahora se centra con ancho ajustado al contenido, separación compacta y buscador limitado a 290 px; en pantallas pequeñas distribuye los controles en dos filas. El menú conserva los 14 tipos dinámicos, Equipamiento sigue retirado y no cambia el contrato de búsqueda.

Los grupos de puntos distintos acercan la cámara hasta separarse por su proyección visual; se quitó el corte anterior en zoom 18. Al límite del motor, la lista permite elegir puntos demasiado próximos. Los avisos con un par de coordenadas idéntico abren un selector de globitos con emoji y precio en círculo. Su distribución es exclusivamente en píxeles dentro del selector: no se escriben, promedian, redondean ni sustituyen coordenadas. Compartir un punto no acredita compartir edificio ni precisión exacta. Cada globito abre su ficha original con fotos, precio y aviso de precisión.

El círculo se ajusta al espacio entre cabecera y filtros, con globitos compactos en celular; si no cabe completo, admite desplazamiento y lo indica. Mover la cámara, cambiar filtros o Escape cierra el selector. Validación Node cubre separación con zoom, apertura/selección/cierre, conservación de coordenadas, texto seguro y círculos sin solapamiento con 2/5/8/18 avisos y dos tamaños de botón. Pasaron 24 pruebas Django de consultas/plantilla, sintaxis y estáticos.

Revisión real en el navegador local: panel compacto en escritorio y celular, catálogo de 14 tipos con emojis, grupo real de cinco avisos con sus cinco globitos visibles en ambas dimensiones, selección de Departamento/Gaggiotti con ficha/fotos/precisión, y separación progresiva de un grupo cercano al acercar. Se restableció el tamaño habitual del navegador después de probar 1280×800 y 390×844. No hubo migraciones, scraping, cambios de datos productivos, commit, push ni despliegue. La publicación sigue a cargo del usuario. El apartado inferior de MapTiler conserva el estado anterior a esta autorización.

### MapTiler y siguiente etapa de interfaz — 13 de octubre de 2026

El usuario activó MapLibre 6.14.0 en la plantilla y después autorizó probar MapTiler para mejorar cobertura de construcciones. Se agregó `MAPTILER_API_KEY` opcional desde `.env`/Environment de Render, transmitida por `json_script` al navegador. Es una clave cartográfica pública, restringida por Allowed HTTP origins en MapTiler; no es la SECRET_KEY de Django ni una credencial del backend. Usar claves separadas para localhost/127.0.0.1 y el dominio productivo; no versionar sus valores. Ver [guía local y Render](docs/mapa.md).

El controlador elige Streets v4 si hay clave y Bright/OpenFreeMap si no la hay. Reutiliza Building 3D del estilo, o su origen building si debe agregar una extrusión, sin descargar edificios de otro proveedor ni duplicar fuentes. Conserva logo MapTiler y atribución. Lee height/height_min de Planet v4 y render_* de OpenMapTiles; el respaldo ilustrativo de 6 m no acredita alturas reales ni precisión de propiedades. No hay fallback automático ante errores de cuota/clave: quitar la variable y reiniciar vuelve a OpenFreeMap.

La clave local guardada por el usuario respondió HTTP 200 a Streets v4; se verificaron Building, Building 3D visible desde zoom 15 y Building number del origen maptiler_planet_v4. Validación: 211 pruebas de propiedades, 209 aprobadas y dos PostGIS omitidas con SQLite; pruebas Node de ambos proveedores/edificios sin duplicación y check/estáticos/sintaxis correctos. No afirmar cobertura completa de Rafaela ni inspección visual real. Sin migraciones, paquetes, ingesta, reconstrucción de Elasticsearch o cambios de datos productivos; commit/push/despliegue siguen a cargo del usuario.

En esta etapa se acordó recuperar colores, tipografía y emojis del diseño anterior, reducir el buscador y expandir visualmente en círculo los avisos compartidos. El usuario pidió primero MapTiler y después la interfaz; posteriormente confirmó MapTiler y autorizó esos cambios. Ver el estado actualizado en el apartado anterior. Equipamiento sigue retirado según su decisión anterior. Las notas inferiores conservan sus estados históricos.

### Mejoras de interfaz y búsqueda por punto — 12 de octubre de 2026

El usuario autorizó implementar diseño propio, agrupación visual, íconos por tipo con precio, menú hamburguesa del catálogo dinámico, buscador libre y panel inferior. Confirmó quitar Equipamiento y buscar alrededor de un punto con 1 km predeterminado y opciones 500 m/1 km/2 km; no pidió herramientas para dibujar radio o rectángulos. El backend ahora limita `radio_m` a 2000 metros, manteniendo la consulta PostGIS y la política de precisión. Los endpoints de rectángulo existentes se conservan, sin nuevo control de dibujo.

Cambios preparados localmente en plantilla/CSS/JavaScript y validación del radio. El mapa recorre todas las páginas de la API, distingue coincidencias y avisos con coordenadas, cancela búsquedas anteriores sin pisar resultados y muestra fallos de Elasticsearch sin reemplazarlo por búsqueda de palabras en el navegador. Comodidades y texto se combinan en `q`; tipo/dormitorios/precio/operación siguen en PostgreSQL. Moneda sin selector: al comparar precios, alquiler ARS y venta USD, conservando la moneda real de cada aviso y limpiando el rango cuando cambia operación.

La agrupación visual usa posiciones en píxeles y ancla el grupo en un punto de sus avisos. No corrige ni desplaza coordenadas, no calcula distancias geográficas y conserva selección/lista/advertencias de precisión del pull. El catálogo sigue siendo dinámico: incluye Campo y los demás tipos disponibles, no una lista fija de 13.

El usuario hará la instalación/activación de MapLibre GL JS + OpenFreeMap. El controlador tiene compatibilidad preparada con cámara inclinada, capa de edificios, marcadores, grupos y punto; la plantilla sigue cargando Leaflet y usa `data-engine="leaflet"`. No presentar la migración como activa. Seguir [docs/mapa.md](docs/mapa.md): cambiar el CSS CDN, `data-engine` y los scripts por la importación de MapLibre y luego del controlador. No exige npm, paquetes Python, claves nuevas, migraciones, scraping ni reconstrucción de Elasticsearch. Diseño WebGL/cobertura 3D reales y revisión visual pendientes.

Validación: 216 pruebas Django, 214 aprobadas y dos integraciones PostGIS omitidas con SQLite; pruebas Node de coordenadas/grupos, íconos/precios, consulta, punto, páginas, errores, concurrencia y adaptador MapLibre con objetos simulados; sintaxis y estáticos verificados. Chromium de prueba no estaba instalado y Edge headless no pudo arrancar: no afirmar inspección visual. No se modificaron datos productivos ni se ejecutaron ingestas. No hubo commit/push/despliegue; el usuario mantiene la publicación. Las secciones históricas que siguen describen etapas previas.

### Workflow de coordenadas: estado operativo informado por el usuario — 12 de octubre de 2026

El usuario compartió logs del workflow con dos aplicaciones iniciales (IDs 527 y 597) y otras seis en un lote ampliado (625, 630, 654, 664, 667, 740): **ocho propiedades Gaggiotti enriquecidas**. El lote ampliado procesó 23 candidatos, con seis aplicados, 14 ambiguos y tres sin resultado; las dos mejoras anteriores se omitieron. Los lotes reutilizan rechazos cacheados, por lo que sus conteos procesados no deben sumarse como filas distintas. Es evidencia aportada por el usuario, sin nueva comprobación independiente de filas/migraciones, API/mapa ni URL/ID de ejecución.

La [guía de coordenadas](docs/geocodificacion.md#ejecutar-desde-github-actions-paso-a-paso) detalla cada campo de Actions, prueba consulta→aplicación, ejecución directa con `todas`/100/0, cursor, caché, interpretación de estados y reversión por comando. `aplicado: true` confirma la escritura de esa ejecución; `ya_enriquecida` describe la instantánea anterior. Menos candidatos que el límite termina ese recorrido elegible, sin garantizar ubicaciones precisas para todas las publicaciones. No hace falta scraping ni reconstrucción de Elasticsearch después de aplicar. Mantener la exclusión con ingesta y las políticas del proveedor. El usuario mantiene el push de nuevas modificaciones de documentación.

### Tipos dinámicos en el mapa — 12 de octubre de 2026

Por observación del usuario, se reemplazaron los cuatro tipos fijos del mapa por un catálogo generado desde todos los tipos no vacíos de publicaciones vigentes en venta o alquiler. Se consulta una sola vez al renderizar la página, mediante DISTINCT en PostgreSQL/SQLite; no depende de los primeros 100 resultados ni consulta Elasticsearch. Conserva el filtro exacto por `tipo`, las categorías originales y los manejadores existentes. Tipos nuevos aparecen al recargar, sin modificar código; se excluyen categorías únicamente históricas/inactivas. Sin datos se informa que no hay tipos disponibles.

Verificación de solo lectura en Supabase: 14 categorías vigentes (Campo, Casa, Chacra, Cochera, Consultorio, Departamento, Depósito, Galpón, Local, Nave Industrial, Oficina, PH, Quinta, Terreno). Los botones se ajustan a varias filas en escritorio y mantienen desplazamiento horizontal en pantallas pequeñas. La mejora está local, pendiente de push/despliegue; por sí sola no necesita migraciones, variables ni repetir scraping. Si se publica junto con coordenadas, sigue siendo necesaria `0013`. Dos pruebas cubren catálogo independiente de paginación, categorías nuevas, vacíos/inactivas y aplicación real del filtro en API. Ver [API y tipos disponibles](docs/api_propiedades.md#tipos-disponibles-en-el-mapa).

### Coordenadas: diagnóstico, enriquecimiento y aplicaciones productivas informadas — 12 de octubre de 2026

El usuario aprobó diagnosticar puntos repetidos, validar direcciones mediante Nominatim, conservar los originales y agrupar puntos compartidos en el mapa. `propiedades/coordenadas.py` detecta cinco avisos y cinco puertas distintas reconocibles en un mismo punto/fuente/localidad; también utiliza `APPROXIMATE`/`GEOMETRIC_CENTER` de `gmLocationType`, ahora conservado por Gaggiotti. Unidades de una misma puerta no cuentan como direcciones distintas. El umbral es configurable; una señal no prueba que el punto sea incorrecto.

`0013_evidencia_coordenadas` agrega `coordenadas_fuente`, `geocodificacion`, `metodo_ubicacion_fuente` y `ConsultaDireccion`. Solo una coincidencia única de calle, altura, localidad, país y provincia conocida permite mejorar el punto efectivo. Se rechazan resultados de calle/barrio, direcciones ambiguas y localidades inferidas. No se promueve exactitud: `ubicacion_aproximada=NULL`, sin radio inventado, precisión API `geocodificada_direccion`; los filtros PostGIS siguen requiriendo `incluir_aproximadas=1`. El original queda separado y restaurable. No se indexan coordenadas en Elasticsearch.

La ingesta preserva mejoras cuando dirección y punto/precisión/radio originales coinciden (conocer o actualizar solamente el método no las invalida); cambios las invalidan y errores de ficha las conservan. Refresca y concilia bajo bloqueo antes de guardar para no pisar una mejora aplicada durante el HTTP. El enriquecimiento revalida y bloquea solo la escritura, nunca durante HTTP. No reemplaza la exclusión operativa entre procesos que consultan al proveedor.

Comandos: `diagnosticar_coordenadas` y `enriquecer_coordenadas` sin flags son vistas previas sin HTTP/escrituras; `--consultar` solo consulta y escribe caché; `--aplicar` corrige resultados aceptados. `--fuente`, `--umbral`, `--limite` (1–100, defecto 10) y `--desde-id` permiten lotes. `restaurar_coordenadas --id ID [--aplicar]` revierte una mejora con vista previa por defecto. Actions incorpora modos explícitos de diagnóstico/enriquecimiento con la concurrencia existente; no se agrega enriquecimiento a la programación semanal ni se exige Elasticsearch para estos modos.

Caché por dirección/proveedor/versión: 30 días para resultados y negativos, 24 horas para errores; el respaldo experimental también se cachea con otro contrato, sin acreditar alturas. Directa e inversa comparten limitador de 15,1 segundos (cuatro consultas/minuto), sin reintentos. Mantener un solo proceso/máquina que consulte el proveedor público, atribución y uso en lotes pequeños; para uso regular de mayor volumen cambiar de proveedor compatible mediante variables opcionales `NOMINATIM_DOMAIN`/`NOMINATIM_USER_AGENT` (Repository Variables en Actions). Leer la [política pública](https://operations.osmfoundation.org/policies/nominatim/). Nunca geocodificar al visitar mapa, API, filtros o health.

API agrega `ubicacion_info`. El mapa agrupa puntos idénticos con una lista de avisos, sin redondear ni desplazar pines, y muestra precisión/atribución en la tarjeta. Reemplaza la dispersión artificial de la versión anterior. La agrupación opera sobre los resultados cargados; no modifica la lógica espacial ni resuelve los límites anteriores de paginación del frontend.

Revisión productiva de solo lectura anterior al despliegue de coordenadas: `0012` aplicada, 754 filas históricas y 752 vigentes, Gaggiotti 306. Health, API paginada con fotos y mapa públicos responden 200; `ubicacion_info` no estaba desplegado en esa revisión. Los cambios anteriores se publicaron en `1f45fc6` y `fdca4d2`; las secciones inferiores conservan el estado histórico de su preparación. Diagnóstico final reproducido en memoria: un punto de Gaggiotti compartido por 18 avisos, con 12 puertas inequívocas y seis no elegibles. Otro grupo textual de cinco no alcanza cinco puertas reconocibles. Seis consultas reales pequeñas: tres rechazadas y tres aceptadas (14 de Julio 829, Belgrano 269, 25 de Mayo 575), sin aplicar resultados ni escribir en Supabase/Elastic. Ver [evidencia, comandos, publicación y límites](docs/geocodificacion.md).

Validación: 212 pruebas Django, 210 aprobadas y dos integraciones PostGIS omitidas con SQLite; migración 0012→0013 y diagnóstico sobre copia efímera, pruebas de caché, reingesta, cambios durante HTTP, invalidación y reversión. Node verifica agrupación/selección/precisión con DOM/Leaflet simulados; actionlint, migraciones y dependencias comprobados. No hubo inspección visual de navegador ni cambios en db.sqlite3. Después de esa validación, el usuario compartió logs de aplicación productiva; ver el estado operativo al comienzo de esta sección. La comprobación posterior de API/mapa sigue pendiente. No requiere dependencias ni Secrets nuevos. El usuario mantiene el push; no reutilizar la autorización histórica limitada a Gaggiotti.

### Frontend y mapa interactivo implementados localmente — 12 de octubre de 2026

El usuario consultó y aprobó la implementación del frontend sobre el stack nativo del repositorio (Opción A: sin frameworks pesados ni bundlers externos como React o Vue). La interfaz principal de mapa está disponible en `/propiedades/mapa/` y toma como referencia visual y funcional a `cocosabe.online`.

Tecnologías frontend utilizadas:
- **HTML5 (Django Templates)**: Plantilla `propiedades/templates/propiedades/mapa.html` servida directamente desde el backend mediante la vista `mapa_propiedades` en `propiedades/views.py`.
- **CSS3 Moderno**: Hoja de estilos `propiedades/static/propiedades/mapa.css` con estética *Glassmorphism* (fondo translúcido con `backdrop-filter: blur`, bordes brillantes y sombras multicapa suaves), tipografía *Plus Jakarta Sans*, micro-interacciones con curvas de resorte (`cubic-bezier`), hover glow en botones de filtros y diseño fluido `flex-wrap` adaptable sin recortes.
- **JavaScript Vanilla (ES6+ modular)**: Archivo `propiedades/static/propiedades/mapa.js` con arquitectura orientada a estado reactivo (`state`), sin dependencias de Node.js ni compilación externa. Control de cancelaciones con `AbortController` para evitar condiciones de carrera.
- **Leaflet.js con Esri WorldStreetMap**: Mapa central interactivo 100% gratuito (sin API keys ni marcas de agua) con filtro CSS plateado/monocromático (*Mapbox Light*), centrado fijo en Rafaela (`zoom: 14`), marcadores personalizados con globo de precio (`L.divIcon`), animación elástica de entrada escalonada y dispersión radial anti-superposición para coordenadas duplicadas.
- **Integración con Elasticsearch y Backend**: Los filtros de tipo (`Casa`, `Departamento`, etc.) viajan estructurados a `GET /api/propiedades/`, mientras que las comodidades (`Cochera`, `Patio`, `Pileta`, `Balcón`, `Terraza`) y equipamiento (`Amoblado`, `Aire Acondicionado`) se concatenan en el parámetro `q` para ejecutar la búsqueda de texto completo BM25 en Elasticsearch. Incorpora además un fallback tolerante a fallos para entornos de desarrollo local que no tengan configurado Elastic Cloud en su `.env`.
- **Tarjeta flotante de propiedad**: Superpuesta sobre el mapa con carrusel deslizable de imágenes (`fotos`), indicador de posición, detalles principales (precio, dormitorios, ambientes, baños, comodidades) y botón directo al aviso original en la inmobiliaria.
- Validación: 183 pruebas de Django aprobadas (100% OK), incluyendo verificación unitaria de la vista del mapa y `collectstatic`.

### Fotos implementadas localmente — 12 de octubre de 2026

El usuario aprobó extraer URLs de fotos de las tres fuentes para preparar el frontend. `Propiedad.fotos` es una lista JSON ordenada, HTTPS y sin duplicados; `foto_portada` devuelve la primera o None. La migración `0012_propiedad_fotos` agrega el campo con listas vacías independientes para filas nuevas/existentes. No se descargan ni alojan archivos y no se indexan imágenes en Elasticsearch.

`DetallesPropiedad.fotos` distingue None (ausente/desconocida/invalidada: conservar), [] (vacía confirmada: limpiar) y lista válida (reemplazar en orden). El importador común ya persiste ese contrato mediante `asdict`, conservando fotos ante errores de ficha o galería. Una baja de operación conserva las fotos. Brega/Avantix leen exclusivamente `#ficha_slider .slides` y `li img.zoomImg`, src/data-src; no logos, iconos, Open Graph ni recomendados. Gaggiotti reutiliza `photos` de Search: image, portada isFrontCover y order. Formato inválido emite advertencia, conserva la galería y no impide refrescar el resto del detalle.

La API agrega `fotos` y `foto_portada` sin consultas adicionales. El HTML de prueba muestra portada con lazy load y reemplazo ante error; no se implementó galería interactiva ni frontend definitivo. Las imágenes las solicita el navegador al servidor original; no se garantiza disponibilidad permanente.

Verificación real de lectura: tres fichas Brega con 18/18/15 fotos, tres Avantix con 10/8/1 y 306 publicaciones Gaggiotti con 4.774 fotos, todas sus galerías verificables. Una portada por fuente respondió 200 image/jpeg sin Referer. Reproducción en SQLite en memoria: seis fichas Tokko y 306 Gaggiotti persistidas, repetidas sin duplicados, full_clean y migración 0011→0012 con conservación de fila previa. Sin modificaciones en Supabase, Elastic ni db.sqlite3.

Pendiente publicar y aplicar 0012 antes de la ingesta: Render ya ejecuta migrate/collectstatic en su build; Actions ahora comprueba `migrate --check` antes de Elasticsearch, sin aplicar migraciones. No requiere nuevas variables, Secrets ni dependencias. Una reconstrucción sola no obtiene fotos: ejecutar ingesta después de migrar. No se hizo push ni despliegue de esta etapa. Ver [contrato, pruebas, límites y publicación](docs/fotos.md).

Validación final de fotos: 182 pruebas, 180 aprobadas y dos integraciones PostGIS omitidas con SQLite. `collectstatic`, validación de Actions, sintaxis y reemplazo JavaScript, migraciones completas y dependencias comprobados. La migración está creada y probada en bases efímeras; sigue pendiente de aplicar en Supabase.

### Bajas por operación y mantenimiento implementados localmente — 12 de octubre de 2026

El usuario aprobó conservar los avisos retirados como inactivos, recuperar el índice sin scraping y limpiar versiones conservando la activa y la anterior. Se reutilizan `en_venta`/`en_alquiler`: la presencia en cada listado determina vigencia, sin deducirla del texto de una tarjeta. Las bajas se aplican después de descargar todos los listados y persistir la fuente; ambas operaciones se concilian en una transacción corta. Se conservan filas, detalles y precios; una reaparición reactiva la misma identidad. Una fuente que solo declara una operación no modifica la otra. No se agrega historial de bajas ni columnas nuevas.

Un fallo fatal anterior impide bajas y conserva escrituras previas. Errores recuperables de ficha no indican retirada. Tarjetas omitidas inhiben todas las bajas de la fuente (`bajas_omitidas=1`, revisar aun con job exitoso). Brega/Avantix rechazan HTML sin tarjetas ni `--NoMoreProperties--` y cualquier repetición de IDs durante la paginación. Gaggiotti ya comprueba totales y páginas. Un listado vacío confirmado sí puede desactivar toda una operación. Tokko no ofrece snapshot/total estable: permanece el riesgo de cambios durante la extracción que no generen duplicados.

HTML/API excluyen inactivas por SQL aunque el índice anterior conserve sus IDs. La reconstrucción indexa solo avisos vigentes en alguna operación y registra en `_meta.grupo7` la versión anterior, finalización y conteo antes de activar el alias. Una base con filas todas inactivas puede activar cero documentos; una base realmente vacía exige `--permitir-vacio`.

El workflow incorpora `modo: ingesta|reconstruir|limpiar_indices`. La programación sigue en ingesta; los modos comparten concurrencia. Reconstruir no hace scraping. La limpieza muestra una vista previa por defecto; `--aplicar` local o `aplicar_limpieza` en Actions ejecutan borrados por nombre concreto. Conserva activo, antecesor registrado, índices con otros aliases, formatos ajenos y versiones del mismo segundo/posteriores. Revisa protecciones antes de cada borrado; no sustituye un bloqueo distribuido para comandos locales. Un activo sin metadatos o un antecesor ausente impide borrar: primero reconstruir con el código nuevo. No hay limpieza destructiva semanal automática.

Esta etapa está local, pendiente de publicación y comprobación productiva. No requiere migraciones, dependencias, variables ni Secrets nuevos; verificar permisos de mapping/borrado de la API key. No se hicieron push, ingesta productiva, reconstrucción ni borrados reales. La vista previa contra Elastic conservó los siete índices existentes; el activo `propiedades-20261012101143-5ac7ed47` tiene 754 documentos y todavía no registra antecesor. Los listados públicos Brega/Avantix pasaron la validación nueva: 136/38 y 250/35 venta/alquiler; dos alquileres Brega candidatos a baja, sin aplicar. Ver [política, recuperación, limpieza y publicación](docs/mantenimiento.md). El historial del ping, vencimiento exacto y continuidad de Elastic siguen pendientes de revisar en sus paneles.

Validación final de mantenimiento: 164 pruebas, 162 aprobadas y dos PostGIS omitidas con SQLite; `actionlint` 1.7.12 sin errores, sin migraciones pendientes ni dependencias rotas. Las pruebas de bajas y borrados usan bases efímeras/Elastic simulado; la comprobación real fue exclusivamente de lectura.

### Filtros, paginación y API JSON implementados localmente — 12 de octubre de 2026

Por solicitud del usuario se implementaron juntos los pasos 3 y 4. Plan ejecutado: definir/validar parámetros comunes, filtrar en PostgreSQL/PostGIS, combinar relevancia antes de paginar, exponer HTML/JSON y verificar/documentar. `propiedades/consultas.py` concentra validación, filtros y paginación; ambas vistas reutilizan ese flujo. `/api/propiedades/` devuelve JSON público de solo lectura; `/propiedades/` queda paginado con navegación mínima y conservación de filtros. No se implementó el frontend definitivo ni el mapa.

Parámetros: `operacion` (venta/alquiler, alquiler si se omite), `tipo` (coincidencia completa `iexact`, sin agrupar categorías), `dormitorios` exactos incluyendo cero, `moneda` ARS/USD, `precio_min`/`precio_max` inclusivos con Decimal, `q` y los geográficos existentes. Precio exige operación y moneda explícitas; moneda sola exige operación explícita. Cantidades desconocidas no equivalen a cero. No se convierten monedas. `pagina` empieza en 1, `por_pagina` tiene valor predeterminado 20 y máximo 100. Entradas inválidas/repetidas: 400; página inexistente: 404; servicios de búsqueda/geografía no disponibles: 503. GET/HEAD; otros métodos: 405.

Sin texto se cuenta y pagina SQL con orden `-actualizada_en,-pk`; con texto se lee el ranking completo de Elasticsearch y se intersectan sus IDs con filtros PostgreSQL/PostGIS en lotes de 500 antes de paginar. Solo se recuperan modelos completos de la página. Sigue pendiente optimizar el coste de leer todos los IDs para volúmenes grandes; no se mantienen snapshots entre páginas del visitante. El JSON incluye totales, enlaces relativos, orden, advertencias geográficas, procedencia y ambas operaciones con precios como cadenas decimales. No se filtra geografía ni precio en Elasticsearch.

Validación: 137 pruebas, 135 aprobadas y dos integraciones PostGIS omitidas con SQLite. Sin migraciones pendientes ni dependencias rotas. Las vistas locales se comprobaron además contra los servicios reales en una transacción de solo lectura: 650 ventas y 121 alquileres recorridos por páginas sin pérdidas/duplicados; 47 coincidencias al combinar Casa/dos dormitorios/USD hasta 200.000/cochera/radio de 2 km con aproximadas, con ranking de las primeras dos páginas y totales PostGIS verificados. Se conservaron las 754 publicaciones, sin ingesta ni escritura en Supabase/Elastic.

Esta etapa está pendiente de publicación y comprobación pública. La autorización de push anterior correspondió a Gaggiotti; no se hizo push ni despliegue de filtros/API. No requiere migraciones, variables, dependencias, Secrets ni reconstruir el índice. Ver [contrato, ejemplos, límites y publicación](docs/api_propiedades.md). La siguiente feature es frontend/mapa, después de publicar esta etapa.

### Gaggiotti y tolerancia por fuente publicadas y verificadas — 12 de octubre de 2026

El usuario autorizó explícitamente al agente a hacer commit, push a `main` y ejecutar el workflow para publicar Gaggiotti y la tolerancia por fuente. Esta autorización reemplazó para esta etapa el acuerdo anterior de que el usuario haría el push. Código publicado en `a390093`; [workflow manual exitoso](https://github.com/juampisarra/Grupo7_TAP_SaraSarraWilliner/actions/runs/38213432407), de 03:37:27 a 03:52:17 de Argentina. Las tres fuentes terminaron sin errores de detalle: Avantix actualizó 275, Brega 171 y Gaggiotti creó 306. Brega conserva dos avisos anteriores, conforme a la política de bajas todavía pendiente.

Supabase contiene 754 publicaciones: 173 Brega, 275 Avantix y 306 Gaggiotti. Esta última tiene 264 ventas, 46 alquileres, cuatro compartidas, 306 detalles verificados y puntos PostGIS, 305 ciudades explícitas y precisión desconocida en todos sus puntos. Sin duplicados; los modelos de Gaggiotti pasan validación de campos. El alias de Elasticsearch apunta a `propiedades-20261012065209-0b10f499`; sus 754 documentos coinciden íntegramente en IDs y contenido con PostgreSQL.

Comprobaciones públicas HTTP 200: listados con 264/46 avisos de Gaggiotti y búsqueda `cochera` con 112 ventas/12 alquileres de esa fuente, conservando exactamente el ranking de Elasticsearch. Radio de 2 km en venta desde `-31.25,-61.49`: cero Gaggiotti en modo solo exactas y 119 con `incluir_aproximadas=1`, coincidiendo con PostGIS y mostrando advertencia. Health 200, radio inválido 400 y una ficha original Gaggiotti 200. Suite local previa: 117 pruebas, 116 aprobadas y una PostGIS omitida con SQLite; sin migraciones ni dependencias rotas. Ver [detalle de validación](docs/gaggiotti.md). Las secciones del 11 de octubre que siguen conservan el estado histórico de preparación local.

### Gaggiotti: tercera fuente implementada localmente — 11 de octubre de 2026

El equipo eligió Gaggiotti como tercera inmobiliaria. `AdaptadorGaggiotti` está registrado como `gaggiotti` y guarda procedencia `Gaggiotti`, usando el contrato, importador y persistencia comunes. Su web utiliza un servicio JSON público, distinto de Tokko: `POST /api/Property/Search` realiza búsquedas de solo lectura y devuelve fichas completas paginadas. Se reutilizan dentro de cada instancia después de completar el listado; no se vuelve a pedir cada ficha por HTTP. La consulta directa de detalle sin listado previo conserva GET como respaldo. No necesita migraciones, dependencias, variables ni Secrets nuevos. Ver [implementación y publicación](docs/gaggiotti.md).

Se conservan precios/monedas separados por operación, cero explícito y cantidades desconocidas en NULL. Se respeta `webPrice` y se toma el primer precio publicado de cada operación como el frontend original, sin conversiones. Ciudad/provincia provienen de la jerarquía explícita; no se confunde departamento con ciudad. Sus marcadores no garantizan precisión: `ubicacion_aproximada=NULL`, radio nulo y filtros espaciales con `incluir_aproximadas=1`. No se extrapola la decisión particular sobre Avantix. La geografía sigue exclusivamente en PostGIS.

El relevamiento real obtuvo 264 avisos de venta y 46 de alquiler, cuatro compartidos: 306 únicos. La primera ingesta efímera guardó 306 y verificó 278 fichas; 28 consultas de detalle recibieron HTTP 502. Después de eliminar esas consultas duplicadas, la versión final se validó reproduciendo las 17 respuestas de listado capturadas: 306 altas con detalles y coordenadas, cero errores y 305 ciudades explícitas. La repetición actualizó 306 sin altas ni duplicados. Todos pasaron `full_clean` y serialización al documento de Elasticsearch. Después de otro 502 transitorio, la última extracción en vivo de la versión optimizada obtuvo nuevamente ambas operaciones y parseó los 306 detalles sin errores ni GET de fichas. Esa última extracción no escribió datos; no confundirla con la prueba separada de persistencia mediante respuestas capturadas.

Suite final: 117 pruebas, 116 aprobadas y una integración PostGIS omitida con SQLite. No se modificaron Supabase, Elasticsearch ni la base SQLite local; las bases de prueba se destruyeron. Gaggiotti y la tolerancia por fuente siguen pendientes de push y primera ejecución productiva del workflow. Brega y Avantix mantienen el despliegue confirmado anteriormente.

### Tolerancia a fallos por fuente — 11 de octubre de 2026

Implementada localmente por solicitud del equipo, pendiente de push y comprobación en Actions. `importar_propiedades` aísla excepciones de cada fuente (incluida su inicialización), informa nombre/tipo/causa, continúa con las restantes y enumera completadas/fallidas. Conserva escrituras previas; no captura `KeyboardInterrupt` ni `SystemExit`. Los errores recuperables de fichas individuales mantienen su conteo y comportamiento anteriores.

Salida `0`: todas completadas; `3`: algunas completadas y algunas fallidas; `1`: ninguna completada. El workflow conserva el fallo del paso de ingesta y reconstruye únicamente con código `0` o `3`, sin cancelación. Así incorpora datos guardados aunque exista un fallo parcial y el job sigue fallido para avisarlo. Ante fallo total o de preparación omite reconstrucción. No hay reintentos nuevos ni aislamiento transaccional de una fuente completa. Ver [operación, recuperación y pruebas](docs/ingesta.md).

Validación: 96 pruebas descubiertas, 95 aprobadas y una integración PostGIS omitida con SQLite. Se verificó preservación de datos, repetición sin duplicados, fuente individual/alias, interrupciones y código de salida. El script Bash del workflow se probó con salidas simuladas, sin ingesta real ni cambios en Supabase/Elastic. No requiere migraciones ni nuevos Secrets.

### Integración de Avantix desplegada — 11 de octubre de 2026

Avantix está implementada y registrada como segunda fuente mediante `AdaptadorAvantix`. Brega y Avantix reutilizan parsers comunes de Tokko para listados y campos generales de ficha; la configuración de URLs y la interpretación geográfica permanecen separadas por fuente. El comando específico es `python manage.py importar_propiedades avantix` y el comando sin argumentos recorre ambas fuentes; el workflow existente la incorporó sin cambios ni Secrets adicionales.

La validación pública de solo lectura obtuvo HTTP 200 en `/Venta` y `/Alquiler`, con 20 tarjetas completas en el primer lote de cada operación. `?p=2` devolvió 20 avisos de venta y 15 de alquiler, y `?p=99` terminó sin tarjetas mediante `--NoMoreProperties--`. Una ficha real confirmó `#prop-desc`, `.ficha_detalle_item`, `#lista_informacion_basica` y `.ficha_ul`; el parser obtuvo título, descripción, zona, ambientes, dormitorios y baños.

El mapa de Avantix observado contiene un marcador de Google Maps con coordenadas, pero no publica un círculo ni un radio. Por decisión confirmada del equipo el 11 de octubre, la integración trata ese marcador como una ubicación exacta: lee únicamente `q=latitud,longitud` del iframe de Google Maps dentro de `#ficha_mapa`, valida el par y guarda `ubicacion_aproximada=False` con `radio_ubicacion_m=NULL`. Formatos desconocidos, valores inválidos y varios puntos distintos se descartan. No se reutiliza el lector de círculos de Brega. Esta clasificación como exacta es una decisión del equipo; la fuente no declara explícitamente esa precisión.

Una ingesta real controlada contra la base efímera de pruebas de Django procesó 275 publicaciones únicas: 250 de venta y 35 de alquiler, con superposición entre operaciones. Verificó 274 fichas y continuó correctamente ante un error de detalle; el resumen temporal no conservó la URL ni la causa concreta, por lo que debe revisarse en los logs de la próxima ejecución. Los otros 274 registros obtuvieron título, descripción y dormitorios verificados. Esa ingesta se hizo antes de habilitar la extracción del marcador, por lo que no recibió coordenadas y no mide cuántas fichas actuales las publican. Después se verificó una ficha pública real: el parser obtuvo `-31.250540799413834, -61.49395149727678`, precisión exacta según la decisión del equipo y radio nulo. La base efímera se destruyó al finalizar: no se modificaron `db.sqlite3`, Supabase ni Elasticsearch.

Después del push, el equipo confirmó una ejecución manual exitosa del workflow con ambas inmobiliarias. Supabase muestra 275 registros al filtrar `fuente=Avantix`, con coordenadas cargadas en las filas observadas, y la búsqueda pública devuelve correctamente publicaciones de Brega y Avantix después de reconstruir Elasticsearch. Avantix queda considerada desplegada y operativa; no requirió migraciones, variables de entorno ni Secrets adicionales.

Validación automática posterior: 87 pruebas descubiertas, 86 aprobadas y una integración PostGIS omitida al usar SQLite. La suite incluye el iframe realista de Avantix, punto cero, formatos inválidos o ambiguos y persistencia de `False` sin geocodificación. `makemigrations --check --dry-run` no detectó cambios y `pip check` no encontró dependencias rotas. El comando general procesa las fuentes en orden alfabético (`avantix`, luego `brega`). Los errores de una ficha se aíslan, pero un fallo de listado o paginación de cualquier fuente todavía aborta el comando general y evita la reconstrucción posterior del índice. El equipo acordó implementar más adelante aislamiento por fuente: registrar el fallo, continuar con las fuentes restantes y finalizar informando cuáles fallaron.

### Automatización y búsqueda pública — 11 de octubre de 2026

El equipo cargó los Repository Secrets y comprobó manualmente el workflow completo de GitHub Actions. El job comprueba Elastic Cloud antes de escribir, ejecuta el comando general sin argumentos y reconstruye el índice desde Supabase al finalizar. La primera ejecución informada terminó correctamente en 3 minutos y 53 segundos. El workflow usa `concurrency`, tiene un límite de 60 minutos y queda programado semanalmente para los lunes a las 00:00 de Argentina.

Elasticsearch quedó configurado en Render y el equipo confirmó que la búsqueda pública funciona. `/propiedades/` incorpora un cuadro de texto mínimo para enviar `q`; conserva la operación seleccionada y muestra los resultados en el orden de relevancia recibido desde Elasticsearch. Sigue sin existir mapa, paginación pública ni frontend definitivo.

La automatización actual hace una reconstrucción completa después de cada ingesta, no indexación incremental después de cada propiedad. Ante un fallo durante la reconstrucción, los datos nuevos permanecen en PostgreSQL y el alias anterior de Elasticsearch continúa atendiendo búsquedas. Siguen pendientes la recuperación incremental, una política de limpieza de versiones físicas anteriores y la política de publicaciones retiradas.

La integración de Avantix se apoyó en solicitudes públicas que verificaron que `/Venta` y `/Alquiler` usan tarjetas Tokko con `li[prop-id]`, `.prop-desc-tipo-ub`, `.prop-desc-dir` y `.prop-valor-nro`; `?p=2` devuelve lotes parciales de 20 avisos y las páginas posteriores terminan con `--NoMoreProperties--`. Las fichas comparten `#prop-desc`, `.ficha_detalle_item`, `#lista_informacion_basica` y `.ficha_ul`. A diferencia de Brega, el mapa observado usa un punto de Google Maps sin publicar un radio ni declarar precisión. La precaución inicial de no persistirlo fue reemplazada por la decisión confirmada del equipo de tratarlo como exacto.

### Data API de Supabase desactivada — 11 de octubre de 2026

El Security Advisor de Supabase mostró `RLS Disabled in Public` para las tablas creadas por Django en `public`, incluidas las tablas de autenticación, sesiones, migraciones, `propiedades_propiedad` y `propiedades_consultalocalidad`. El aviso confirmaba que RLS estaba desactivado, pero no indicó una filtración de credenciales ni demostró por sí solo acceso efectivo: ese acceso depende de la combinación de esquemas expuestos, grants y RLS.

El repositorio no usa `supabase-js`, REST, GraphQL, claves `anon` ni la Data API; Django, GitHub Actions y los comandos de mantenimiento se conectan directamente a PostgreSQL mediante psycopg. El equipo desactivó la Data API y comprobó después el listado, la búsqueda textual y un filtro geográfico PostgreSQL/PostGIS. Todo continuó funcionando. La operación no borró datos ni modificó RLS o grants. El Security Advisor puede seguir mostrando el hallazgo porque desactivar la API no activa RLS.

No se encontraron secretos reales versionados: `.env` está ignorado y no aparece en el historial, y GitHub Actions referencia Repository Secrets sin incluir sus valores. No hay una tarea de seguridad abierta por este hallazgo. Si en el futuro se decide reactivar la Data API para consumir Supabase directamente desde un cliente, antes deberán diseñarse RLS, políticas y grants mínimos explícitos. Ver [seguridad de datos](https://supabase.com/docs/guides/database/secure-data) y [seguridad de la Data API](https://supabase.com/docs/guides/api/securing-your-api).

### Elasticsearch y despliegue — 10 de octubre de 2026

El equipo pidió dejar esta etapa documentada para que el compañero propietario de la cuenta de Render publique el código y configure sus variables. No desplegar ni hacer push en su nombre: el usuario hará el push. Seguir la [guía de continuidad](docs/continuidad.md), que distingue `.env` local de Environment en Render y lista las pruebas públicas pendientes.

El equipo confirmó el despliegue de health, plantilla y PostGIS. Se verificaron públicamente `/health/` (200), filtros espaciales (200 y 400 ante entrada inválida) y avisos de precisión. El equipo creó un job de ping en cron-job.org; falta comprobar su historial de ejecución, no asumir que ya funciona regularmente.

Elasticsearch está integrado localmente con el cliente oficial Python 9.5.1 y un proyecto Elastic Cloud que responde como 9.6.0. Las credenciales están en `.env`, sin versionar. El equipo indicó evaluación el martes 13 de octubre; la prueba de 14 días cubre esa fecha, pero falta registrar su vencimiento exacto en el panel.

`comprobar_elasticsearch` valida conexión; `reconstruir_indice` crea una versión completa desde la base configurada y cambia atómicamente el alias `propiedades`, conservando versiones anteriores y rechazando por defecto una base vacía. Se cargaron 173 documentos desde Supabase sin scraping ni cambios de publicaciones. `buscar_propiedades` prueba consultas con score. El analizador es `spanish`, ranking BM25, texto agregado y pesos iniciales por campo. No se indexan precios ni coordenadas para filtrar.

`/propiedades/?q=...` busca texto y combina IDs ordenados con los filtros PostgreSQL/PostGIS, conservando relevancia. Sin texto no consulta Elasticsearch; ante fallos de búsqueda responde 503, sin reemplazar por LIKE. Se usa PIT/search_after para leer todas las coincidencias. El 11 de octubre se agregó un formulario mínimo para `q`; no hay mapa ni paginación pública. Los cambios de operación conservan los parámetros de búsqueda. Pruebas reales: 16 coincidencias para `departamento con cochera` (5 alquiler/11 venta), 2 para `cochera y quincho` y ranking verificado con un índice temporal luego eliminado.

Esta integración Elasticsearch todavía debe configurarse y desplegarse en Render. La indexación automática tras cada guardado no se implementó en esta etapa: después de una ingesta se debe reconstruir manualmente. Recuperación incremental, concurrencia de reconstrucción/ingesta y política de avisos retirados siguen pendientes. Ver [configuración, comandos, límites y validación](docs/elasticsearch.md). El resto de las revisiones fechadas conserva el estado histórico de cada etapa.

Validación final: 72 pruebas descubiertas, 71 aprobadas y una PostGIS omitida en SQLite; sin cambios de modelo pendientes ni dependencias incompatibles. Dos reconstrucciones reales dejaron 173 documentos, un único índice activo por alias y dos versiones físicas conservadas; los IDs coinciden exactamente con Supabase. No se modificaron publicaciones ni se ejecutó ingesta. `.env` sigue ignorado por Git. No se publicó ni desplegó el código de esta etapa.

### Revisión y correcciones del 9 de octubre de 2026

Se verificó `https://observatorio-grupo7.onrender.com/propiedades/`: HTTP 200 para alquiler (40 avisos) y venta (136), estáticos accesibles y redirección HTTP a HTTPS. Supabase conserva 173 publicaciones de Brega sin duplicados, 172 pares completos y 164 entradas de caché. El repositorio es público. Son conteos de esa revisión; ver [informe inicial](docs/revision_2026-10-09.md).

Después, por solicitud del equipo, se implementó `/health/` con GET/HEAD, sin base ni servicios externos, y se corrigió la visualización de valores cero. Con DEBUG=False se exige HTTPS, cookies seguras y HSTS de una hora, sin subdominios ni preload; estas dos recomendaciones de `check --deploy` siguen visibles. El correo está explícitamente deshabilitado en producción mediante un backend que falla ante un intento de envío; no se configuró un proveedor. Se eliminó la definición duplicada de MIDDLEWARE.

Se aplicó `0011_ubicacion_postgis` a Supabase: PostGIS 3.3.7 en `extensions`, columna generada `ubicacion geography(Point,4326)` y dos índices GiST (distancia y área). PostgreSQL deriva el punto de longitud/latitud en cada escritura, sin añadir un campo GeoDjango ni requerir GEOS/GDAL. SQLite omite los objetos espaciales y rechaza filtros geográficos con 503. El backend incorpora filtros GET por radio en metros y rectángulo con bordes incluidos, exclusivamente mediante PostGIS. Por defecto solo usa ubicaciones explícitamente exactas; `incluir_aproximadas=1` incluye centros aproximados y precisión desconocida con advertencia. No se interpreta el círculo como ubicación exacta ni se implementó intersección de áreas de incertidumbre. No hay polígonos arbitrarios todavía. Ver [contrato y límites](docs/postgis.md).

Suite de esa etapa: 55 pruebas en SQLite, 54 aprobadas y una integración PostGIS omitida. Se comprobaron radio, metros, bordes, precisión, nulos, actualizaciones y respuestas HTTP contra PostGIS real en una tabla temporal revertida, conservando las 173 publicaciones. No se ejecutó scraping. Esta descripción registra la preparación del 9 de octubre: el despliegue de esas correcciones se comprobó el 10 y el job de cron-job.org ya fue creado, con historial pendiente de validar. La suite posterior de Elasticsearch descubrió 72 pruebas, 71 aprobadas y una omitida en SQLite.

Al actualizar este contexto, el código contiene:

- Un proyecto Django en `config/` y la aplicación `propiedades/`. `config/database.py` permite SQLite o PostgreSQL según `DB_ENGINE`; `config/settings.py` carga `.env` sin sobrescribir variables del sistema. `.env.example` documenta los valores; no contiene credenciales reales.
- Configuración para el despliegue básico: `DJANGO_SECRET_KEY` obligatorio desde el entorno, `DJANGO_DEBUG` con valor predeterminado False y `DJANGO_ALLOWED_HOSTS` como lista separada por comas. El dominio recibido en `RENDER_EXTERNAL_HOSTNAME` se agrega automáticamente; en Render se configura el encabezado del proxy HTTPS y cookies de sesión/CSRF seguras.
- Gunicorn `26.2.0`, WhiteNoise `6.12.0`, archivos estáticos en `staticfiles/` con almacenamiento comprimido y manifiesto, y `.python-version` con `3.14`. `.env` y `staticfiles/` están excluidos de Git. Comandos de construcción y arranque documentados en [docs/despliegue.md](docs/despliegue.md).
- El modelo `Propiedad`, con fuente, identificador de origen, dirección, tipo, dormitorios y su estado de verificación, operaciones de venta/alquiler, precios y monedas separados por operación, URL original, fecha de actualización y latitud/longitud opcionales. PostgreSQL deriva de estos FloatField la columna espacial generada `ubicacion`; SQLite conserva solo los campos portátiles.
- Ampliación acotada del modelo en la migración `0008`: título, descripción, características como texto, ciudad, provincia, zona, ambientes y baños. Dormitorios ya existía. No se agregan columnas para cada amenidad: cochera, parrilla y otras características se conservan en el texto extraído. Los textos faltantes quedan vacíos y las cantidades desconocidas en NULL; cero es un valor válido.
- La migración `0009` agrega `ubicacion_aproximada` (NULL: precisión desconocida; False: punto tratado como exacto; True: la fuente publica un área) y `radio_ubicacion_m` opcional. Un círculo no representa una dirección exacta ni garantiza que la propiedad esté en su centro. Avantix queda como False por decisión del equipo aunque la fuente no declare explícitamente la precisión de su marcador.
- Una restricción única por `(fuente, identificador_fuente)` y persistencia común con `update_or_create` en `propiedades/ingesta.py`.
- Un scraper Brega en `propiedades/scraping/brega.py` que consulta `/Venta` y `/Alquiler` con Requests y Beautiful Soup, recorre páginas con `p`, evita identificadores repetidos y termina ante un lote vacío o sin identificadores nuevos. Tiene un límite de seguridad de 50 páginas, timeout de 15 segundos y pausas de 0,5 segundos; no tiene reintentos implementados.
- Normalización básica de precios, monedas, tipos y operaciones en `propiedades/scraping/normalizacion.py`. El contrato `PublicacionNormalizada` y el protocolo `AdaptadorFuente` están en `propiedades/scraping/contratos.py`; `AdaptadorBrega` traduce la extracción existente a ese contrato.
- El flujo común `importar_fuente` en `propiedades/ingesta.py` consolida operaciones/precios, obtiene una ficha completa por aviso en cada ingesta, gestiona coordenadas y persiste. Las fuentes se registran en `propiedades/scraping/fuentes.py`: Brega, Avantix y Gaggiotti. Esta última reutiliza la ficha completa recibida en el listado actual. Ya no se omiten fichas por tener dormitorios verificados: también deben refrescarse descripción y características. Si falla la ficha se conservan los detalles guardados; la ausencia de un dato nuevo (None) tampoco borra el anterior. La detección de datos retirados de una ficha queda pendiente.
- `python manage.py importar_propiedades brega`, `python manage.py importar_propiedades avantix` y `python manage.py importar_propiedades gaggiotti` importan una fuente específica; el mismo comando sin argumentos importa todas en orden `avantix`, `brega`, `gaggiotti`. `python manage.py importar_brega` se conserva como alias compatible.
- Geocodificación experimental con geopy/Nominatim en `propiedades/scraping/geocoding.py`, limitada a direcciones con ciudad explícita y con separación mínima de 1,5 segundos entre consultas por proceso. Sin ciudad no se consulta el proveedor: no se supone Rafaela ni se deducen localidades por nombres de calles.
- Si cambia dirección, ciudad, provincia o zona, se invalidan ambas coordenadas anteriores y se intenta resolver la nueva ubicación solo si hay ciudad explícita. Si no se encuentra o el proveedor falla, quedan vacías; los errores del proveedor se registran. Un par incompleto también se invalida y se intenta completar. Un par completo se reutiliza si la ubicación no cambió, incluso si alguna coordenada vale cero.
- Brega extrae el título Open Graph, descripción de `#prop-desc` (limpiando HTML escapado, con respaldo Open Graph), características de `.ficha_ul`, cantidades de `.ficha_detalle_item`/`#lista_informacion_basica` y ubicación textual. El rótulo `Ubicación` puede ser localidad o barrio: se guarda como `zona`, nunca se transforma automáticamente en ciudad. Ciudad/provincia solo se extraen si aparecen con esos rótulos explícitos.
- Brega ahora extrae también el par latitud/longitud y radio del `L.circle([latitud, longitud], radio, {...})` publicado dentro de `#ficha_mapa`, sin ejecutar JavaScript ni consultar servicios adicionales. En tres fichas reales se verificaron círculos distintos con radio de 400 metros. No se extrae el centro de `setView`, ni mapas del footer, ni se fija 400 como valor universal. Formatos no reconocidos quedan sin coordenadas nuevas; valores fuera de rango, radios inválidos o varios círculos distintos se descartan con advertencia.
- Avantix extrae únicamente el parámetro `q=latitud,longitud` del iframe de Google Maps contenido en `#ficha_mapa`. Guarda el par como exacto (`ubicacion_aproximada=False`) y sin radio por decisión del equipo. No interpreta marcadores JavaScript, direcciones dentro de `q`, iframes externos al mapa ni varios puntos distintos.
- Las coordenadas válidas de la fuente tienen prioridad sobre la geocodificación, incluso sin ciudad; se renuevan en cada ingesta y conservan precisión/radio. Sin coordenadas de fuente se mantiene la lógica de invalidación y geocodificación con ciudad explícita. No se mezclan pares parciales con datos anteriores. Al invalidar coordenadas también se borra precisión/radio. Las coordenadas históricas conservadas no se consideran auditadas.
- Geocodificación inversa opcional en `propiedades/enriquecimiento.py`, activada únicamente con `--completar-ubicacion`. Completa ciudad/provincia faltantes, sin modificar coordenadas, zona ni precisión. La migración `0010` agrega `ciudad_origen`, `provincia_origen` y el modelo `ConsultaLocalidad` para caché persistente por par de coordenadas. Origen `fuente` identifica valores explícitos recibidos en la ingesta; `nominatim_inversa` identifica nombres inferidos. El origen vacío de datos históricos significa procedencia no registrada, no una inferencia confirmada.
- La caché guarda respuestas resueltas, vacías, ambiguas y errores. Las respuestas no fallidas se reutilizan sin nueva consulta; los errores temporales se reintentan después de 24 horas. Cambiar las coordenadas selecciona otra entrada de caché y borra solo nombres inferidos del punto anterior, incluso sin activar el enriquecimiento. Los datos explícitos siempre tienen prioridad y los nombres inferidos no se usan para volver a geocodificar una dirección.
- El enriquecimiento acepta `city`/`town`/`village` y `state` con país `ar`; no confunde barrio o departamento con ciudad. Rechaza localidades contradictorias, estructuras inválidas y resultados incompatibles con valores ya conocidos. Una respuesta parcial puede completar solo uno de los campos. Estos controles no detectan si el círculo aproximado cruza límites administrativos: los nombres siguen siendo inferencias, no datos garantizados. No se calculan límites ni distancias en Python.
- Las consultas directas e inversas a Nominatim comparten un limitador de 1,5 segundos, sin reintentos inmediatos. Ejecutar un solo job que utilice el proveedor público a la vez; la limitación es por proceso y no coordina procesos distintos. Fallos del proveedor se registran y permiten continuar guardando publicaciones.
- Una vista y plantilla en `/propiedades/` que consultan datos guardados, filtran por venta o alquiler, permiten enviar una búsqueda textual simple y enlazan al aviso original. El filtro predeterminado es alquiler.

La conexión y las migraciones hasta `0011` se verificaron en Supabase/PostgreSQL. La revisión de solo lectura del 8 de octubre de 2026 encontró 173 publicaciones: 172 con coordenadas completas, 170 con `ciudad_origen=nominatim_inversa`, 172 con `provincia_origen=nominatim_inversa` y 164 entradas de caché. Estos conteos son una instantánea, no valores esperados fijos ni una validación individual de precisión. Se comprobó además el proveedor con tres puntos: Bella Italia devolvió Bella Italia/Santa Fe; Barrio 30 de Octubre devolvió Rafaela/Santa Fe; Lehmann devolvió Municipio de Lehmann/Santa Fe.

PostGIS, Elasticsearch, formulario textual mínimo, GitHub Actions, tolerancia por fuente y las tres inmobiliarias están publicados y verificados. Supabase contiene 754 publicaciones en la comprobación del 12 de octubre. Filtros de tipo/dormitorios/precio, API JSON y paginación están implementados y probados localmente, pendientes de publicar. No hay frontend definitivo ni mapa. `/health/` ya está desplegado; el ping externo fue creado y falta verificar su historial. Para ejecutar pruebas en PowerShell sin usar Supabase, configurar antes una `DJANGO_SECRET_KEY` de desarrollo:

```powershell
$env:DB_ENGINE = "sqlite"
.\.venv\Scripts\python.exe -X utf8 manage.py collectstatic --noinput
.\.venv\Scripts\python.exe -X utf8 manage.py test propiedades config
Remove-Item Env:DB_ENGINE
```

El ejemplo supone que no había una variable de sistema `DB_ENGINE` previamente definida en esa terminal; si la había, guardar y restaurar su valor. La selección temporal de SQLite evita crear una base de pruebas en Supabase. `collectstatic` prepara el manifiesto utilizado por la plantilla con DEBUG=False; solo genera archivos ignorados en staticfiles/, sin consultar la base. También se verificaron ausencia de cambios de modelo sin migración (`makemigrations --check --dry-run`) y dependencias instaladas (`pip check`).

## Ejecutar la ingesta local

Para instalar dependencias, configurar `.env`, conectar Supabase y conservar datos de SQLite, seguir [docs/base_de_datos.md](docs/base_de_datos.md). La selección es `DB_ENGINE=sqlite` (predeterminado) o `DB_ENGINE=postgresql` con `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD` y `PGSSLMODE`. PostgreSQL usa TLS por defecto. No se guardan credenciales en el código ni se requiere una API key de Supabase. Ejecutar migraciones antes de la ingesta. La exportación/importación documentada está destinada a un PostgreSQL vacío, no a mezclar bases con publicaciones existentes. En Windows usar `python.exe -X utf8` para `dumpdata`/`loaddata` y conservar correctamente los acentos.

Están registradas e ingeridas en producción Brega, Avantix y Gaggiotti. `importar_propiedades` lleva un guion bajo y la clave de fuente se escribe en minúsculas. Desde la raíz del proyecto, en PowerShell:

```powershell
.\.venv\Scripts\python.exe manage.py importar_propiedades brega
.\.venv\Scripts\python.exe manage.py importar_propiedades avantix
.\.venv\Scripts\python.exe manage.py importar_propiedades gaggiotti
```

El nombre de fuente es opcional: si se indica, debe ser una fuente registrada y no una URL; si se omite, el comando importa todas las fuentes registradas en un solo proceso. La forma específica es `python manage.py importar_propiedades <fuente>`, reemplazando `<fuente>` por `brega`, `avantix` o `gaggiotti`, sin los signos `<` y `>`. Escribir otro nombre no agrega soporte automáticamente. Reutilizar el importador y la persistencia existentes.

Para completar opcionalmente ciudad/provincia faltantes desde las coordenadas, usando la caché persistente:

```powershell
.\.venv\Scripts\python.exe manage.py importar_propiedades brega --completar-ubicacion
```

El alias `importar_brega` también admite `--completar-ubicacion`. Sin esa opción no se hacen consultas inversas nuevas. El resumen incluye `Localidades completadas`, que cuenta avisos donde se completó al menos un campo, incluso desde caché. Los cambios de coordenadas siempre invalidan nombres inferidos anteriores.

## Arquitectura y flujos esperados

```text
Job Python en GitHub Actions (semanal y manual)
  ├─ Scraper/adaptador Brega (disponible)
  ├─ Scraper/adaptador Avantix (desplegado)
  └─ Scraper/adaptador Gaggiotti (publicado y verificado)
                   │
                   ▼
             Normalización común
                   │
                   ▼
     Supabase / PostgreSQL con PostGIS
                   │
                   ▼
    Indexación en Elasticsearch / Elastic Cloud

Frontend futuro + mapa → Django en Render
                           ├─ Elasticsearch: texto y relevancia
                           └─ PostgreSQL + PostGIS: datos y filtros
                        → Respuesta única al frontend
```

El scraping se ejecuta separado de las consultas de los usuarios: una visita, un cambio de filtro o un ping al servicio web no dispara pedidos a los sitios externos. El usuario consulta la última información guardada. GitHub Actions ejecuta semanalmente la ingesta y reconstrucción completa del índice; el comando manual se conserva para desarrollo y recuperación.

Separar scraping, normalización, acceso a base de datos, indexación, búsqueda textual, consultas geográficas y API. Mantener una solución modular y entendible; no crear tres sistemas independientes ni introducir microservicios, colas u otras capas sin necesidad.

El backend Python coordina las consultas y devuelve un único conjunto de resultados. El frontend no debe acceder directamente a Elasticsearch ni a la base de datos.

## Ingesta y modelo normalizado común

Preparar desde el comienzo una estructura común para aproximadamente tres inmobiliarias. Cada fuente tendrá su scraper/adaptador y configuración; todos deberán producir el mismo modelo normalizado. Se puede compartir un adaptador entre fuentes de la misma plataforma cuando se compruebe su compatibilidad. La lógica específica de cada sitio debe quedar separada de la persistencia, normalización e indexación comunes.

Implementación común actual: cada adaptador expone `nombre`, `operaciones`, `extraer(operacion)` y `extraer_detalles(url)`. `extraer` devuelve objetos `PublicacionNormalizada`, uno por aviso y operación, con precio/moneda de ese listado. `extraer_detalles` devuelve `DetallesPropiedad` con datos opcionales de la ficha; los errores de lectura deben propagarse. El núcleo consolida por identificador dentro de cada fuente y mantiene precios separados. Para incorporar una fuente, implementar ese contrato y registrarla, sin copiar el importador. Brega y Avantix reutilizan los parsers Tokko de listado y ficha; cada módulo conserva URLs, paginación y cualquier interpretación geográfica específica. Avantix interpreta el punto verificado de Google Maps como exacto por decisión del equipo y lo deja sin radio.

Ciudad/provincia y zona se persisten cuando se aportan, sin inferirlas por el foco del proyecto. La reconstrucción completa del índice desde PostgreSQL está implementada y GitHub Actions la ejecuta tras la ingesta; la persistencia sigue concentrada en `guardar_publicacion`. La indexación incremental después de guardar y su recuperación específica siguen pendientes. La política de publicaciones retiradas está confirmada e implementada localmente: conservar la fila y desactivar por operación después de completar la fuente; publicación pendiente. Ver [mantenimiento](docs/mantenimiento.md).

Los datos a contemplar, según lo que realmente proporcione cada fuente, incluyen:

- Identificador de la publicación y la inmobiliaria de origen.
- Tipo de propiedad y operación: venta, alquiler o ambas cuando corresponda.
- Precio y moneda por operación; conservar los campos separados existentes cuando una publicación ofrezca venta y alquiler.
- Dirección, ciudad, barrio o zona.
- Dormitorios, ambientes y superficie con su unidad.
- Título, descripción y características disponibles.
- URL original e imágenes.
- Latitud, longitud y una representación compatible con PostGIS cuando existan coordenadas.

El contrato común incluye latitud/longitud opcionales, indicación de ubicación aproximada y radio publicado en metros. La extracción y validación numérica no realizan consultas geográficas. Los futuros filtros PostGIS deben contemplar la incertidumbre de las áreas publicadas; no tratar sus centros como ubicaciones exactas.

Estos son objetivos del modelo común, no campos ya implementados en su totalidad. Representar los datos faltantes sin inventarlos y distinguir ausencia de información de errores de lectura. No asumir que todas las publicaciones tienen coordenadas ni completar su ciudad únicamente por el foco inicial en Rafaela. Mantener diferenciadas monedas y unidades: un filtro de precio debe indicar la moneda y la operación para comparar valores correctamente.

El job debe crear publicaciones nuevas y actualizar las existentes sin duplicarlas al repetir una carga. Conservar la identidad `(fuente, identificador_fuente)` y la procedencia. Detectar la misma propiedad anunciada por inmobiliarias diferentes es un problema distinto; su alcance sigue pendiente.

La sincronización acordada es:

`Scraper → normalización → PostgreSQL → indexación en Elasticsearch`.

Primero persistir en PostgreSQL y después indexar. El índice debe poder reconstruirse completamente desde las propiedades guardadas en PostgreSQL si se pierde. Al implementar esta integración, definir cómo reintentar o recuperar indexaciones fallidas sin perder datos ni crear duplicados; no dar por resuelta la sincronización entre ambos servicios.

## Búsqueda de texto completo

Utilizar Elasticsearch como motor real de búsqueda; una consulta SQL con `LIKE` no cumple esta feature. PostgreSQL conserva los datos completos y la autoridad sobre ellos.

El objetivo académico incluye documentos, términos, índices invertidos, posting lists, frecuencia de términos, rareza de términos, relevancia y ranking con BM25. Por ejemplo, un índice invertido relaciona `cochera → [propiedad 2, propiedad 8, propiedad 15]` y `quincho → [propiedad 3, propiedad 8]`. Los términos menos frecuentes pueden aportar mayor poder discriminante a la relevancia.

Una búsqueda como `departamento con cochera y quincho` debe devolver resultados ordenados por relevancia, no limitarse a comprobar si aparece cualquiera de las palabras. Los campos candidatos a indexar incluyen título, descripción, dirección, barrio, ciudad, tipo de propiedad y características disponibles.

Contemplar el análisis del texto en español y las stopwords, como `para`, `la`, `el`, `de`, `con` e `y`. La configuración concreta de analizadores, campos y pesos se definirá al implementar y probar el buscador. Elasticsearch se utilizará únicamente para texto y relevancia; toda la lógica geográfica corresponde a PostGIS.

## Filtros estructurados y combinación de resultados

La búsqueda implementada localmente combina texto libre/relevancia con tipo de inmueble, dormitorios exactos, operación, precio mínimo/máximo, moneda y ubicación. HTML y API JSON comparten filtros y paginación. El contrato está documentado en [API de propiedades](docs/api_propiedades.md). Ambientes, superficie y otros filtros siguen como ampliaciones posibles.

- Elasticsearch encuentra y ordena las coincidencias textuales.
- PostgreSQL aplica los filtros estructurados y entrega los datos completos.
- PostGIS aplica los filtros geográficos dentro de PostgreSQL.
- El backend coordina estos resultados y devuelve propiedades que cumplen todas las condiciones solicitadas, conservando el ranking textual cuando haya una búsqueda de texto.

Ejemplo: `departamento con cochera`, operación alquiler, tipo departamento, precio máximo ARS 700.000 y radio de 2 km desde un punto seleccionado. El backend combina relevancia de Elasticsearch, precio/operación/tipo de PostgreSQL y distancia de PostGIS. Sin texto libre consulta PostgreSQL/PostGIS sin Elasticsearch. La paginación se aplica después de todos los filtros; con texto mantiene el ranking y sin texto ordena por actualización e ID descendentes.

## Geografía exclusivamente con PostGIS

Guardar las coordenadas disponibles en PostgreSQL y utilizarlas mediante una representación espacial de PostGIS. El prototipo incluye geocodificación experimental mediante geopy/Nominatim, únicamente con ciudad explícita. Su uso definitivo, validación de precisión y extracción de localidad siguen pendientes. No inventar ubicaciones para datos ausentes. No se implementaron filtros espaciales fuera de PostGIS.

Las modalidades previstas son:

| Modalidad | Entrada al backend | Consulta prevista en PostGIS |
| --- | --- | --- |
| Radio | Latitud, longitud y radio con su unidad; por ejemplo, 2 km. | Determinar qué propiedades están dentro de la distancia, evaluando `ST_DWithin` según el modelo espacial elegido. |
| Área | Rectángulo/bounding box o geometría/puntos de un polígono seleccionado o dibujado. | Determinar qué propiedades están dentro del área, evaluando `ST_Within`, `ST_Contains`, intersecciones u operaciones de bounding box según corresponda. |

Definir la representación espacial, el sistema de referencia, las unidades de distancia y el tratamiento de los límites del área antes de elegir las funciones concretas. Evaluar índices espaciales como GiST para evitar recorridos completos en cada consulta. PostGIS es la única tecnología responsable de coordenadas y consultas espaciales: no implementar distancia, radio, bounding boxes ni polígonos en Elasticsearch.

El frontend futuro permitirá seleccionar un punto/radio o dibujar un área en un mapa, de forma similar a Airbnb; el cálculo y filtrado geográficos estarán en el backend mediante PostGIS.

## Fuentes exploradas y reutilización

Brega, Avantix y Gaggiotti tienen scrapers registrados y validados mediante el workflow, datos en Supabase y búsquedas públicas. Gaggiotti utiliza un adaptador independiente para su servicio JSON público y reutiliza el flujo común. Ver [Gaggiotti](docs/gaggiotti.md).

- Brega: https://www.bregainmobiliaria.ar
- Avantix: https://www.avantix.ar
- Gaggiotti: https://www.gaggiotti.com.ar

La exploración mediante solicitudes directas confirmó en ambos sitios un patrón compatible con Tokko: elementos `li[prop-id]`, clases `.prop-desc-dir`, `.prop-desc-tipo-ub` y `.prop-valor-nro`, un primer lote en el HTML y carga adicional mediante `?p=2`, con lotes de 20 en Avantix y marcador `--NoMoreProperties--` al finalizar.

Las fichas Avantix verificadas también comparten `.ficha_detalle_item`, `#lista_informacion_basica`, `.ficha_ul` y `#prop-desc`. El código reutiliza esos parsers sin mezclar la geografía: Brega publica un `L.circle` con radio y Avantix expone un punto en Google Maps que el equipo decidió clasificar como exacto y sin radio. No fijar una cantidad universal de páginas ni asumir que todos los sitios Tokko son idénticos.

Compartir la extracción Tokko verificada de listados, paginación y campos comunes de ficha. Mantener en cada fuente la configuración de nombre, URL base, URLs de búsqueda y cualquier extracción geográfica cuya semántica difiera.

## Plan incremental acordado

1. Ampliar el contrato y flujo de ingesta común ya implementados con los datos adicionales que aporten las fuentes, manteniendo separada la extracción específica.
2. Completar la primera inmobiliaria de punta a punta: extracción, modelo normalizado, persistencia en Supabase/PostgreSQL e indexación en Elasticsearch.
3. Verificar altas, actualizaciones, ausencia de duplicados por fuente y reconstrucción del índice desde PostgreSQL; probar búsqueda textual y ranking.
4. Incorporar la segunda inmobiliaria y después la tercera, reutilizando el flujo común y verificando los datos de cada fuente.
5. PostGIS básico implementado y desplegado: almacenamiento generado, radio y rectángulo con índices GiST. Falta ampliar a polígonos y definir el tratamiento de áreas de incertidumbre.
6. Preparar la búsqueda del backend que combine texto, filtros estructurados y filtros geográficos. Desarrollar frontend y mapa posteriormente.

Las prioridades inmediatas son arquitectura de scrapers, modelo común, persistencia, job de ingesta, integración/indexación/búsqueda con Elasticsearch y soporte geográfico con PostGIS. El plan conserva las etapas originales; el soporte PostGIS básico ya se implementó por solicitud posterior del equipo. Las demás features indicadas como pendientes no están terminadas.

### Avance del despliegue y siguiente paso

El despliegue básico, health, PostGIS, Elasticsearch público, el formulario textual mínimo y GitHub Actions ya están comprobados. Avantix reutiliza la extracción Tokko verificada, persiste el punto validado de su mapa como exacto y sin radio por decisión del equipo, y ya fue ingerida en Supabase e incorporada al índice público.

1. Parsers comunes de listado y ficha, y recorrido común de paginación extraídos sin alterar el comportamiento verificado de Brega; cada fuente conserva sus URLs, solicitudes y configuración.
2. `AdaptadorAvantix` implementado y registrado, con pruebas de listados, operaciones dobles, precios, detalles, registro y terminación/límite de páginas.
3. Extracción pública, ingesta efímera local, ingesta real en Supabase y reconstrucción de Elasticsearch validadas mediante el workflow.
4. Identidad por fuente y resultados públicos comprobados. El 12 de octubre se publicaron la tolerancia por fuente y Gaggiotti; el workflow completo y los datos/resultados de las tres fuentes quedaron verificados. El aislamiento ante fallos está cubierto por pruebas locales; la ejecución productiva terminó con las tres fuentes exitosas.

El despliegue de la segunda fuente comprueba la extensibilidad del importador común; no completa las features pendientes ni requiere definir una nueva interfaz.

## Próximos cinco pasos acordados

1. **Tolerancia a fallos por fuente: completada y publicada.** Aislamiento probado localmente y workflow publicado/verificado con ejecución exitosa de las tres fuentes. Continúa con las restantes y reconstruye ante éxito parcial, manteniendo el job fallido. Ver [ingesta](docs/ingesta.md).
2. **Tercera inmobiliaria: completada y publicada.** Gaggiotti ingerida en Supabase, indexada y comprobada en búsquedas públicas. Ver [Gaggiotti](docs/gaggiotti.md).
3. **Filtros estructurados: implementados localmente.** Tipo, dormitorios y precios inclusivos separados por operación/moneda. Falta publicar y comprobar en Render.
4. **Paginación y API JSON: implementadas localmente.** HTML y `/api/propiedades/` comparten filtros, totales y orden; publicación pendiente. Ver [contrato](docs/api_propiedades.md).
5. **Frontend y mapa: implementados por el equipo y ruta pública comprobada.** Django Templates, JavaScript y Leaflet en `/propiedades/mapa/`; mantener la lógica espacial en el backend. El enriquecimiento de coordenadas tiene ocho aplicaciones productivas informadas por el usuario; quedan por comprobar API/mapa después de aplicarlas y revisar los límites de carga/paginación del frontend.

En paralelo con el primer paso, comprobar el historial del ping y el vencimiento exacto de Elastic Cloud. Estas tareas operativas no reemplazan los cinco pasos funcionales.

## Decisiones de implementación pendientes

- Tolerancia por fuente y Gaggiotti publicadas y verificadas el 12 de octubre. No son tareas pendientes; seguir con filtros estructurados.
- Traslado de datos locales si se desea conservar información que no esté en la ingesta de Supabase; política de intersección de áreas de incertidumbre, polígonos arbitrarios y futuras ampliaciones del esquema común; la representación espacial y los filtros básicos ya están implementados. El proyecto Supabase, conexión y migraciones hasta `0011` están verificados.
- [X] Workflow y frecuencia en GitHub Actions: lunes a las 00:00 de Argentina, ejecución manual, Secrets, exclusión de simultaneidad, comprobación previa de Elastic e indexación completa posterior verificadas.
- [ ] Indexación/recuperación incremental pendiente. Reconstrucción independiente y limpieza con vista previa implementadas localmente; publicar y comprobar.
- [X] Política de retirados confirmada: desactivar por operación y conservar. Implementada localmente junto con recuperación completa independiente; pendiente de publicación. Ver [mantenimiento](docs/mantenimiento.md).
- Comprobación del historial de cron-job.org y del intervalo guardado; `/health/` ya está desplegada y el job fue creado.
- Publicación y comprobación pública de filtros/paginación/API ya implementados localmente; optimización futura del ranking completo y ajuste de relevancia. Elasticsearch en Render y reconstrucción automática posterior a la ingesta ya funcionan.
- Validación del geocodificador experimental, extracción explícita de ciudad/provincia, auditoría de coordenadas históricas y tratamiento definitivo de ubicaciones ausentes.
- Publicación y validación del enriquecimiento de coordenadas y agrupación de puntos; tecnología frontend ya adoptada por el equipo (Django Templates/JavaScript/Leaflet).
- Registro del vencimiento exacto de la prueba de Elastic Cloud y continuidad posterior; configuración y comprobación de Django en Render con Elasticsearch. El servicio Elastic y su índice ya existen; el despliegue básico con Supabase ya funciona.

Requests y Beautiful Soup ya se usan para Brega. Comprobar primero si las consultas directas permiten obtener los datos de cada nueva fuente; no dar por necesaria la automatización de un navegador. No se ha adoptado React, un framework de scraping adicional, colas de tareas ni microservicios. El despliegue del sitio es un requisito de entrega; Django ya está alojado en Render y no se ha adoptado Vercel.

## Criterios de trabajo

- Revisar el estado real del repositorio antes de hacer cambios grandes y respetar sus convenciones cuando sean razonables.
- Priorizar una solución clara, modular y mantenible para un trabajo práctico universitario. Explicar las decisiones y los conceptos nuevos de forma sencilla.
- Avanzar por pasos pequeños que el equipo pueda ejecutar y comprender; agregar nuevas fuentes sin modificar fuertemente el núcleo.
- Consultar las fuentes con tiempos de espera, ritmo moderado y reintentos limitados; evitar bucles de paginación y cargas duplicadas.
- Verificar extracción y normalización con ejemplos reales; diferenciar datos ausentes de errores y conservar procedencia, monedas y unidades.
- Mantener separadas ingesta y búsquedas, persistencia e índice textual, y consultas textuales y geográficas.
- No presentar tareas pendientes como funcionalidades existentes ni implementar frontend sin la necesidad de prueba indicada o una instrucción posterior del equipo.

## Referencia compartida

Resumen de la idea en el Google Doc «Lluvia de Ideas», pestaña «Idea del TP»:
https://docs.google.com/document/d/1HiQLoD9vaR4fEAyy5bm_5d_fspXELkBCkJn2u0wkB3A/edit?tab=t.xl5s41rt5ksx

Este AGENTS.md contiene el contexto necesario para comenzar sin depender del acceso a la conversación o al documento externo. Las instrucciones explícitas posteriores del equipo prevalecen sobre este contexto.
