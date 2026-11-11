"""Fuentes de datos: cómo armar la URL de cada sitio y cómo leer (parsear) lo que devuelve.

Cada módulo tiene funciones PURAS: reciben texto o bytes y devuelven datos. No hacen solicitudes;
de eso se encarga ``radar.red.ClienteHttp``. Así cada parser se prueba con las páginas guardadas en
``fixtures/`` sin usar internet, y el mismo código sirve en modo vivo y en modo replay.

Fuentes elegidas (justificación y evidencia en docs/adr/004-fuentes-de-datos.md):

| Módulo         | Sitio            | Tipo de dato                                | Método |
|----------------|------------------|---------------------------------------------|--------|
| metacritic.py  | Metacritic       | Descubrimiento (etapa 0), calificación, imagen | HTML   |
| steam.py       | Steam            | Precios (tienda de plataforma), reseñas de usuarios | HTML   |
| nintendo.py    | Nintendo eShop   | Precios (tienda de plataforma)              | HTML   |
| gog.py         | GOG              | Precios (tienda de plataforma)              | API    |
| bestbuy.py     | Best Buy         | Precios (minorista)                         | HTML   |
"""
