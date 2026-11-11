# ADR-012 · Mostrar precios en colones y euros · 2026-11-11

## Contexto
Los precios se obtienen y se guardan en USD (ADR-005). El equipo pidió que el sitio permita verlos en colones
(público de Costa Rica) y en euros, con un selector global (página de ofertas, se recuerda) y uno local (página
de cada juego, solo esa página). Hace falta un tipo de cambio diario que incluya CRC.

## Alternativas
1. **API abierta de ExchangeRate-API (open.er-api.com)** — Ventajas: sin clave ni registro; incluye CRC y EUR;
   se actualiza una vez al día; permite caché. Desventajas: pide atribución visible; límite de consultas (una por
   hora es segura); no permite redistribuir los datos.
2. **Servicio web del Banco Central de Costa Rica** — Ventajas: tipo de cambio oficial del colón. Desventajas:
   exige registrarse con nombre y correo para obtener un token (datos personales de un integrante); no da EUR directo.
3. **Frankfurter (tasas del BCE)** — Ventajas: sin clave. Desventajas: no incluye el colón.

## Decisión
Alternativa 1. El pipeline la consulta una vez por corrida con el mismo `ClienteHttp` (robots.txt, límite por
dominio, caché de 12 h) y publica solo las tasas de CRC y EUR en `datos/tipo_cambio.json`. La conversión es solo
de presentación en el navegador: la base, las ofertas, los mínimos y los experimentos siguen en USD. El pie de
las páginas que convierten muestra la fecha de las tasas y el enlace de atribución.

## Consecuencias
- Se gana: precios en la moneda local sin tocar los datos ni los 3 modos de ejecución.
- Se pierde: el monto convertido es aproximado (las tiendas cobran en USD); se avisa en la página del juego.
- Si la API falla, se conserva el archivo anterior; si nunca hubo uno, el sitio solo ofrece USD.

## Estado
Aceptada (pedido del equipo; revisar en la próxima reunión).
