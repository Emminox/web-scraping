-- =============================================================================
-- Esquema de la base de datos del Radar de Ofertas Multinúcleo (ADR-003: SQLite)
-- =============================================================================
-- Versión del esquema: 1 (se guarda en PRAGMA user_version; ver radar/bd/conexion.py).
-- Explicación completa y diagrama: docs/esquema-bd.md
--
-- Convenciones:
--  * Tablas STRICT: SQLite comprueba el tipo de cada columna. Sin STRICT, SQLite aceptaría guardar
--    el texto "gratis" en una columna de precio sin quejarse.
--  * Dinero en CENTAVOS (INTEGER): 59.99 USD se guarda como 5999. Los números con decimales (REAL)
--    tienen errores de redondeo (0.1 + 0.2 = 0.30000000000000004) que harían fallar comparaciones
--    como "¿el precio actual iguala el mínimo histórico?".
--  * Fechas como TEXT en formato ISO-8601 y en UTC ('2026-11-11T14:30:00+00:00'). En ese formato el
--    orden alfabético coincide con el orden cronológico, así que ORDER BY y MAX funcionan bien.
--  * Booleanos como INTEGER 0/1 con CHECK (SQLite no tiene tipo booleano).
--  * Las tablas observacion_* SOLO admiten INSERT: un trigger impide modificarlas. Así se cumple
--    "el repositorio conserva cada observación de precio en lugar de sobrescribirla" (sección 9).
--  * Todo usa IF NOT EXISTS / OR IGNORE: ejecutar este archivo dos veces no rompe nada.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. Tablas de referencia
-- -----------------------------------------------------------------------------

-- Plataformas en las que sale un juego. "familia" agrupa generaciones para los filtros del sitio
-- (el usuario filtra por "PlayStation" sin tener que elegir PS4 o PS5).
CREATE TABLE IF NOT EXISTS plataforma (
    codigo  TEXT PRIMARY KEY,        -- Identificador corto: 'ps5', 'switch', 'pc'...
    nombre  TEXT NOT NULL,           -- Nombre para mostrar en el sitio.
    familia TEXT NOT NULL CHECK (familia IN ('playstation', 'nintendo', 'xbox', 'pc'))
) STRICT;

-- Datos de referencia fijos (no son el catálogo de juegos, que nunca va en el código).
INSERT OR IGNORE INTO plataforma (codigo, nombre, familia) VALUES
    ('ps4',         'PlayStation 4',     'playstation'),
    ('ps5',         'PlayStation 5',     'playstation'),
    ('switch',      'Nintendo Switch',   'nintendo'),
    ('switch2',     'Nintendo Switch 2', 'nintendo'),
    ('xbox-one',    'Xbox One',          'xbox'),
    ('xbox-series', 'Xbox Series X|S',   'xbox'),
    ('pc',          'PC',                'pc');

-- Cada fuente de datos consultada. Un mismo sitio puede aparecer varias veces si cumple varios
-- papeles (p. ej. 'steam-listado' para descubrir, 'steam-precios' como tienda y 'steam-resenas'
-- como calificación). Las métricas por sitio del panel se agrupan por "dominio".
CREATE TABLE IF NOT EXISTS fuente (
    id      INTEGER PRIMARY KEY,
    codigo  TEXT NOT NULL UNIQUE,    -- Identificador estable usado por el código: 'metacritic', 'hltb'...
    nombre  TEXT NOT NULL,
    tipo    TEXT NOT NULL CHECK (tipo IN (
                'descubrimiento', 'tienda_plataforma', 'minorista',
                'calificacion', 'duracion', 'imagen')),
    dominio TEXT NOT NULL,           -- 'store.steampowered.com'; enlaza con las métricas de red.
    -- Cómo se obtienen los datos. El enunciado exige al menos 3 fuentes por 'html' (2 de ellas tiendas).
    metodo  TEXT NOT NULL CHECK (metodo IN ('html', 'api', 'navegador')),
    activa  INTEGER NOT NULL DEFAULT 1 CHECK (activa IN (0, 1))  -- 0 = sustituida (ver su ADR).
) STRICT;


-- -----------------------------------------------------------------------------
-- 2. Catálogo de juegos (el "repositorio" del enunciado, sección 4)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS juego (
    id               INTEGER PRIMARY KEY,
    -- Identificador estable que viene del archivo de catálogo (p. ej. 'god-of-war-2018').
    -- Permite recargar el catálogo sin duplicar juegos. NO se usa el título como clave porque dos
    -- juegos distintos pueden llamarse igual ("God of War" de 2005 y de 2018: un caso difícil).
    clave            TEXT NOT NULL UNIQUE,
    titulo_canonico  TEXT NOT NULL,
    tipo             TEXT NOT NULL DEFAULT 'juego'
                     CHECK (tipo IN ('juego', 'juego_dlc', 'dlc', 'otro')),  -- Filtro "tipo" del sitio.
    -- Casos difíciles para el emparejamiento (se exigen al menos 50).
    es_caso_dificil  INTEGER NOT NULL DEFAULT 0 CHECK (es_caso_dificil IN (0, 1)),
    categoria_dificultad TEXT CHECK (categoria_dificultad IN (
                         'remasterizacion', 'edicion', 'secuela', 'numeros_romanos',
                         'subtitulo', 'caracteres_especiales', 'otro')),
    imagen_url       TEXT,
    imagen_fuente_id INTEGER REFERENCES fuente (id),
    -- De dónde salió: del listado público (etapa 0) o agregado a mano por el equipo.
    origen           TEXT NOT NULL CHECK (origen IN ('descubrimiento', 'manual')),
    descubierto_por  INTEGER REFERENCES fuente (id),
    -- "Quitar" un juego del catálogo = activo 0. No se borra para no perder su historial de precios.
    activo           INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    agregado_en      TEXT NOT NULL,
    -- Coherencia: solo un caso difícil puede tener categoría de dificultad.
    CHECK (es_caso_dificil = 1 OR categoria_dificultad IS NULL)
) STRICT;

-- Otros nombres con los que se conoce un juego ("Zelda BOTW", "The Legend of Zelda: Breath of the Wild").
-- Son la entrada principal del emparejamiento.
CREATE TABLE IF NOT EXISTS titulo_alternativo (
    juego_id INTEGER NOT NULL REFERENCES juego (id) ON DELETE CASCADE,
    titulo   TEXT NOT NULL,
    PRIMARY KEY (juego_id, titulo)
) STRICT;

-- En qué plataformas sale cada juego. La fecha y el MSRP van aquí y no en "juego" porque varían
-- por plataforma (la versión de Switch suele salir después y costar distinto).
CREATE TABLE IF NOT EXISTS juego_plataforma (
    juego_id          INTEGER NOT NULL REFERENCES juego (id) ON DELETE CASCADE,
    plataforma_codigo TEXT NOT NULL REFERENCES plataforma (codigo),
    fecha_lanzamiento TEXT,                                     -- 'AAAA-MM-DD'
    msrp_centavos     INTEGER CHECK (msrp_centavos > 0),        -- Precio de referencia (MSRP).
    PRIMARY KEY (juego_id, plataforma_codigo)
) STRICT;


-- -----------------------------------------------------------------------------
-- 3. Productos de las tiendas y emparejamiento (sección 6)
-- -----------------------------------------------------------------------------

-- Cada resultado que devuelve una tienda (una ficha de producto con su URL). La etapa de
-- emparejamiento decide a qué juego del catálogo corresponde. Estos campos SÍ se actualizan:
-- si se mejora el algoritmo, el emparejamiento se recalcula.
CREATE TABLE IF NOT EXISTS producto_tienda (
    id                    INTEGER PRIMARY KEY,
    fuente_id             INTEGER NOT NULL REFERENCES fuente (id),
    url                   TEXT NOT NULL,         -- Enlace a la página del producto (se muestra en el sitio).
    titulo_en_tienda      TEXT NOT NULL,         -- Como lo nombra la tienda, sin normalizar.
    plataforma_codigo     TEXT REFERENCES plataforma (codigo),
    formato               TEXT NOT NULL CHECK (formato IN ('fisico', 'digital')),
    tipo                  TEXT CHECK (tipo IN ('juego', 'juego_dlc', 'dlc', 'otro')),  -- Según la tienda.
    -- Resultado del emparejamiento.
    juego_id              INTEGER REFERENCES juego (id) ON DELETE SET NULL,
    similitud             REAL CHECK (similitud BETWEEN 0.0 AND 1.0),
    estado_emparejamiento TEXT NOT NULL DEFAULT 'pendiente'
                          CHECK (estado_emparejamiento IN ('pendiente', 'aceptado', 'dudoso', 'rechazado')),
    motivo_duda           TEXT,                  -- 'cerca del umbral', 'bundle', 'DLC'... (panel de métricas).
    visto_por_primera_vez TEXT NOT NULL,
    UNIQUE (fuente_id, url),                     -- La misma ficha de la misma tienda se guarda una sola vez.
    -- Un producto aceptado o dudoso debe apuntar a un juego.
    CHECK (estado_emparejamiento NOT IN ('aceptado', 'dudoso') OR juego_id IS NOT NULL)
) STRICT;

CREATE INDEX IF NOT EXISTS ix_producto_juego ON producto_tienda (juego_id);


-- -----------------------------------------------------------------------------
-- 4. Ejecuciones del pipeline (panel de métricas, sección 9)
-- -----------------------------------------------------------------------------

-- Una fila por cada vez que corre el pipeline. Toda observación apunta a la ejecución que la
-- produjo; así se sabe qué dato es de la última corrida y cuál quedó desactualizado.
CREATE TABLE IF NOT EXISTS ejecucion (
    id            INTEGER PRIMARY KEY,
    iniciada_en   TEXT NOT NULL,
    terminada_en  TEXT,
    modo          TEXT NOT NULL CHECK (modo IN ('secuencial', 'concurrente', 'paralelo')),
    fuente_datos  TEXT NOT NULL CHECK (fuente_datos IN ('vivo', 'replay')),
    -- Copia en JSON de la configuración usada (workers, colas, latencia...). Sirve para saber con
    -- exactitud cómo se obtuvo cada resultado y poder repetirlo.
    configuracion TEXT NOT NULL,
    estado        TEXT NOT NULL DEFAULT 'en_curso'
                  CHECK (estado IN ('en_curso', 'completa', 'fallida')),
    CHECK (terminada_en IS NULL OR terminada_en >= iniciada_en)
) STRICT;

-- Tiempo de cada etapa en una ejecución ("tiempo por etapa" del panel).
CREATE TABLE IF NOT EXISTS ejecucion_etapa (
    ejecucion_id      INTEGER NOT NULL REFERENCES ejecucion (id) ON DELETE CASCADE,
    etapa             TEXT NOT NULL CHECK (etapa IN (
                          'descubrir', 'descargar', 'parsear', 'emparejar', 'persistir', 'publicar')),
    duracion_segundos REAL NOT NULL CHECK (duracion_segundos >= 0),
    elementos         INTEGER NOT NULL DEFAULT 0,   -- Cuántos elementos procesó la etapa.
    PRIMARY KEY (ejecucion_id, etapa)
) STRICT;

-- Solicitudes por sitio en una ejecución: es la "instantánea" de radar.red.metricas.MetricasRed.
CREATE TABLE IF NOT EXISTS ejecucion_metricas_dominio (
    ejecucion_id      INTEGER NOT NULL REFERENCES ejecucion (id) ON DELETE CASCADE,
    dominio           TEXT NOT NULL,
    exitosas          INTEGER NOT NULL DEFAULT 0,
    reintentos        INTEGER NOT NULL DEFAULT 0,
    fallidas          INTEGER NOT NULL DEFAULT 0,
    desde_almacen     INTEGER NOT NULL DEFAULT 0,
    bloqueadas_robots INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ejecucion_id, dominio)
) STRICT;

-- Cola de fallidos (sección 8): lo que falló, con qué error y si el reintento final lo resolvió.
CREATE TABLE IF NOT EXISTS fallo (
    id                   INTEGER PRIMARY KEY,
    ejecucion_id         INTEGER NOT NULL REFERENCES ejecucion (id) ON DELETE CASCADE,
    url                  TEXT NOT NULL,
    dominio              TEXT NOT NULL,
    juego_id             INTEGER REFERENCES juego (id) ON DELETE SET NULL,
    tipo_error           TEXT NOT NULL,          -- Nombre de la excepción: 'ReintentosAgotados', 'SinCaptura'...
    mensaje              TEXT NOT NULL,
    intentos             INTEGER NOT NULL CHECK (intentos >= 1),
    resuelto_al_final    INTEGER NOT NULL DEFAULT 0 CHECK (resuelto_al_final IN (0, 1))
) STRICT;


-- -----------------------------------------------------------------------------
-- 5. Observaciones (SOLO INSERT): precios, calificaciones y duraciones
-- -----------------------------------------------------------------------------
-- "obtenida_en" es la fecha en que el dato se descargó del sitio (Respuesta.obtenida_en). Si un
-- precio se reutilizó de la caché, conserva su fecha original: el sitio nunca muestra un dato
-- viejo como si fuera de hoy.

CREATE TABLE IF NOT EXISTS observacion_precio (
    id                      INTEGER PRIMARY KEY,
    producto_id             INTEGER NOT NULL REFERENCES producto_tienda (id) ON DELETE CASCADE,
    ejecucion_id            INTEGER NOT NULL REFERENCES ejecucion (id),
    obtenida_en             TEXT NOT NULL,
    precio_actual_centavos  INTEGER NOT NULL CHECK (precio_actual_centavos >= 0),  -- 0 = gratis.
    precio_regular_centavos INTEGER CHECK (precio_regular_centavos >= 0),  -- Precio tachado, si el sitio lo muestra.
    moneda                  TEXT NOT NULL DEFAULT 'USD' CHECK (length(moneda) = 3),
    -- Evita guardar dos veces el mismo producto en la misma ejecución (p. ej. si un reintento
    -- de la cola de fallidos vuelve a procesarlo).
    UNIQUE (producto_id, ejecucion_id)
) STRICT;

-- Índice para encontrar rápido la observación más reciente de cada producto.
CREATE INDEX IF NOT EXISTS ix_precio_producto_fecha ON observacion_precio (producto_id, obtenida_en);

CREATE TABLE IF NOT EXISTS observacion_calificacion (
    id                INTEGER PRIMARY KEY,
    juego_id          INTEGER NOT NULL REFERENCES juego (id) ON DELETE CASCADE,
    fuente_id         INTEGER NOT NULL REFERENCES fuente (id),
    plataforma_codigo TEXT REFERENCES plataforma (codigo),  -- NULL si la fuente no distingue plataforma.
    puntaje           REAL NOT NULL CHECK (puntaje >= 0),
    escala            INTEGER NOT NULL CHECK (escala IN (5, 10, 100)),  -- Metacritic usa 100; usuarios, 10.
    cantidad_resenas  INTEGER CHECK (cantidad_resenas >= 0),
    ejecucion_id      INTEGER NOT NULL REFERENCES ejecucion (id),
    obtenida_en       TEXT NOT NULL,
    CHECK (puntaje <= escala)
) STRICT;

-- Una calificación por juego, fuente, plataforma y ejecución. Se usa un índice con COALESCE porque
-- en una restricción UNIQUE normal SQLite considera distintos dos NULL, y permitiría duplicados
-- cuando la plataforma es NULL.
CREATE UNIQUE INDEX IF NOT EXISTS ux_calificacion
    ON observacion_calificacion (juego_id, fuente_id, COALESCE(plataforma_codigo, ''), ejecucion_id);

CREATE TABLE IF NOT EXISTS observacion_duracion (
    id                INTEGER PRIMARY KEY,
    juego_id          INTEGER NOT NULL REFERENCES juego (id) ON DELETE CASCADE,
    fuente_id         INTEGER NOT NULL REFERENCES fuente (id),
    -- Horas según How Long To Beat. Pueden faltar si el sitio no tiene suficientes datos.
    principal_horas   REAL CHECK (principal_horas > 0),     -- Historia principal.
    extras_horas      REAL CHECK (extras_horas > 0),        -- Historia + extras.
    completista_horas REAL CHECK (completista_horas > 0),   -- Completista.
    ejecucion_id      INTEGER NOT NULL REFERENCES ejecucion (id),
    obtenida_en       TEXT NOT NULL,
    UNIQUE (juego_id, fuente_id, ejecucion_id)
) STRICT;

-- Triggers que hacen las observaciones de solo-inserción: cualquier UPDATE se rechaza con un error.
-- (Borrar sí se permite, para poder eliminar un producto o un juego con todo su historial si hiciera falta.)
CREATE TRIGGER IF NOT EXISTS tr_precio_inmutable BEFORE UPDATE ON observacion_precio
BEGIN
    SELECT RAISE(ABORT, 'Las observaciones de precio no se modifican: inserte una nueva');
END;

CREATE TRIGGER IF NOT EXISTS tr_calificacion_inmutable BEFORE UPDATE ON observacion_calificacion
BEGIN
    SELECT RAISE(ABORT, 'Las observaciones de calificación no se modifican: inserte una nueva');
END;

CREATE TRIGGER IF NOT EXISTS tr_duracion_inmutable BEFORE UPDATE ON observacion_duracion
BEGIN
    SELECT RAISE(ABORT, 'Las observaciones de duración no se modifican: inserte una nueva');
END;


-- -----------------------------------------------------------------------------
-- 6. Vistas de consulta para el sitio
-- -----------------------------------------------------------------------------
-- La definición de "oferta" NO se guarda: depende de un ADR todavía pendiente y se calculará a
-- partir de estas vistas (precio actual vs MSRP y/o vs precio regular).

-- Último precio de cada producto, con la marca de si está desactualizado.
-- "Desactualizado" = la observación más reciente no es de la última ejecución en vivo (p. ej. la
-- tienda falló hoy y lo último que tenemos es de ayer). El sitio debe mostrarlo con su fecha.
CREATE VIEW IF NOT EXISTS v_ultimo_precio AS
WITH ultima_ejecucion_vivo AS (
    -- Se toma la ejecución en vivo más reciente aunque siga 'en_curso', porque la etapa Publicar
    -- corre antes de que la ejecución se marque como 'completa'.
    SELECT MAX(id) AS id FROM ejecucion WHERE fuente_datos = 'vivo' AND estado <> 'fallida'
),
ordenadas AS (
    SELECT o.*,
           ROW_NUMBER() OVER (PARTITION BY o.producto_id
                              ORDER BY o.obtenida_en DESC, o.id DESC) AS posicion
    FROM observacion_precio AS o
)
SELECT ordenadas.producto_id,
       ordenadas.ejecucion_id,
       ordenadas.obtenida_en,
       ordenadas.precio_actual_centavos,
       ordenadas.precio_regular_centavos,
       ordenadas.moneda,
       (ordenadas.ejecucion_id IS NOT (SELECT id FROM ultima_ejecucion_vivo)) AS desactualizado
FROM ordenadas
WHERE posicion = 1;

-- Precio mínimo registrado por juego y formato, contando solo productos bien emparejados.
-- La card muestra "mínimo histórico" cuando el mejor precio actual iguala o mejora este valor.
CREATE VIEW IF NOT EXISTS v_minimo_historico AS
SELECT p.juego_id,
       p.formato,
       MIN(o.precio_actual_centavos) AS minimo_centavos
FROM observacion_precio AS o
JOIN producto_tienda AS p ON p.id = o.producto_id
WHERE p.estado_emparejamiento = 'aceptado'
GROUP BY p.juego_id, p.formato;
