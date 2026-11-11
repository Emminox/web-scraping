# ADR-005 · Definición de "oferta" y origen del MSRP · 2026-11-11

## Contexto
El enunciado pide definir qué significa "estar en oferta" (precio menor que el MSRP del repositorio, menor que
el precio tachado del sitio o un criterio combinado) y guardar un MSRP por juego. Ninguna fuente pública da el
MSRP del fabricante; las tiendas oficiales (Steam, Nintendo eShop, GOG) sí muestran su precio regular.

## Alternativas
1. **Solo MSRP** — Ventajas: una referencia única por plataforma. Desventajas: si el MSRP es viejo (el
   fabricante bajó el precio de lista), marcaría "oferta" un precio que ya es el normal.
2. **Solo precio tachado del sitio** — Ventajas: refleja lo que la tienda declara como descuento. Desventajas:
   las tiendas que no muestran precio regular nunca tendrían ofertas.
3. **Combinado** — precio tachado si la tienda lo muestra; si no, MSRP.

## Decisión
Combinado. **En oferta** = precio actual < precio regular que muestra la tienda; si la tienda no muestra uno
distinto, precio actual < MSRP de esa plataforma. **MSRP** por plataforma = el precio regular de la tienda
oficial preferida (Steam > Nintendo eShop > GOG) la primera vez que se observa; no se sobrescribe después.

## Consecuencias
- Se gana: ofertas coherentes con lo que muestran las tiendas y una referencia estable para comparar.
- Se pierde: plataformas sin tienda oficial consultada (PS5, Xbox) no tienen MSRP automático; se puede
  cargar a mano en `catalogo/*.json`.
- Qué medir: % de juegos con MSRP y diferencias entre MSRP y precio regular de los minoristas.

## Estado
Aceptada (decisión delegada por el equipo; revisar en la próxima reunión).
