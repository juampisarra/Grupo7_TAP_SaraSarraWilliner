"""Columna espacial generada: no requiere GEOS/GDAL ni cambios al ORM portátil."""

from django.db import migrations


def instalar(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    # Limitar la espera si otro proceso está utilizando la tabla.
    schema_editor.execute("SET LOCAL lock_timeout = '5s'")
    schema_editor.execute('CREATE SCHEMA IF NOT EXISTS extensions')
    schema_editor.execute('CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA extensions')
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            SELECT n.nspname FROM pg_extension e
            JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'postgis'
        """)
        schema = schema_editor.quote_name(cursor.fetchone()[0])
    tabla = schema_editor.quote_name(apps.get_model("propiedades", "Propiedad")._meta.db_table)
    schema_editor.execute(f"""
        ALTER TABLE {tabla} ADD COLUMN ubicacion {schema}.geography(Point, 4326)
        GENERATED ALWAYS AS (
            CASE WHEN latitud BETWEEN -90 AND 90 AND longitud BETWEEN -180 AND 180
            THEN {schema}.ST_SetSRID({schema}.ST_MakePoint(longitud, latitud), 4326)::{schema}.geography
            ELSE NULL END
        ) STORED
    """)
    schema_editor.execute(f'CREATE INDEX propiedad_ubicacion_gist ON {tabla} USING GIST (ubicacion)')
    schema_editor.execute(f'CREATE INDEX propiedad_ubicacion_geom_gist ON {tabla} USING GIST ((ubicacion::{schema}.geometry))')


def desinstalar(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        tabla = schema_editor.quote_name(apps.get_model("propiedades", "Propiedad")._meta.db_table)
        # Los índices dependientes se eliminan con la columna. Conservar la extensión compartida.
        schema_editor.execute(f'ALTER TABLE {tabla} DROP COLUMN ubicacion')


class Migration(migrations.Migration):
    dependencies = [("propiedades", "0010_propiedad_ciudad_origen_propiedad_provincia_origen_and_more")]
    operations = [migrations.RunPython(instalar, desinstalar)]
