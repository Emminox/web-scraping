// Radar de Ofertas Multinúcleo · lógica del sitio estático (sin dependencias externas).
//
// Los datos los genera el pipeline (etapa 5) en la carpeta datos/:
//   datos/juegos.json            -> tarjetas de la página de resultados
//   datos/juegos/<clave>.json    -> detalle de cada juego (precios, calificaciones, historial)
//   datos/metricas.json          -> panel de métricas
//
// SEGURIDAD: los títulos y nombres vienen de sitios externos. Nunca se insertan como HTML (innerHTML);
// siempre como texto (textContent). Los enlaces e imágenes solo se aceptan si usan https.
"use strict";

const POR_PAGINA = 24;
const $ = (selector) => document.querySelector(selector);

/** Crea un elemento. `atributos.text` va como texto plano; el resto como atributos. */
function el(etiqueta, atributos = {}, ...hijos) {
  const nodo = document.createElement(etiqueta);
  for (const [clave, valor] of Object.entries(atributos)) {
    if (valor === null || valor === undefined || valor === false) continue;
    if (clave === "text") nodo.textContent = valor;
    else if (clave === "class") nodo.className = valor;
    else nodo.setAttribute(clave, valor);
  }
  for (const hijo of hijos) if (hijo !== null && hijo !== undefined) nodo.append(hijo);
  return nodo;
}

/** Devuelve la URL solo si es https (evita enlaces "javascript:" u otros esquemas peligrosos). */
function urlSegura(url) {
  try {
    const u = new URL(url);
    return u.protocol === "https:" ? u.href : null;
  } catch {
    return null;
  }
}

const precio = (centavos) => (centavos === null || centavos === undefined ? "—" : "$" + (centavos / 100).toFixed(2));
const fecha = (iso) => (iso ? new Date(iso).toLocaleString("es-CR", { dateStyle: "medium", timeStyle: "short" }) : "—");
const segundos = (s) => (s === null || s === undefined ? "—" : s.toFixed(2) + " s");

async function cargar(ruta) {
  const respuesta = await fetch(ruta, { cache: "no-cache" });
  if (!respuesta.ok) throw new Error(`No se pudo cargar ${ruta} (HTTP ${respuesta.status})`);
  return respuesta.json();
}

function mostrarActualizacion(iso) {
  const pie = $("#actualizado");
  if (pie) pie.textContent = "Última actualización: " + fecha(iso);
}

function mostrarError(contenedor, error) {
  contenedor.replaceChildren(el("p", { class: "error", text: "Error: " + error.message }));
}

// ---------------------------------------------------------------------------------------------
// Página de resultados
// ---------------------------------------------------------------------------------------------

async function paginaResultados() {
  let datos;
  try {
    datos = await cargar("datos/juegos.json");
  } catch (error) {
    mostrarError($("#rejilla"), error);
    return;
  }
  mostrarActualizacion(datos.generado_en);

  for (const [codigo, nombre] of Object.entries(datos.familias)) {
    $("#filtro-plataforma").append(el("option", { value: codigo, text: nombre }));
  }
  for (const [codigo, nombre] of Object.entries(datos.tiendas)) {
    $("#filtro-tienda").append(el("option", { value: codigo, text: nombre }));
  }

  let pagina = 1;
  const controles = ["#buscar", "#filtro-tipo", "#filtro-plataforma", "#filtro-formato", "#filtro-tienda", "#solo-ofertas", "#orden"];
  for (const selector of controles) {
    $(selector).addEventListener("input", () => { pagina = 1; dibujar(); });
  }
  $("#anterior").addEventListener("click", () => { pagina -= 1; dibujar(); });
  $("#siguiente").addEventListener("click", () => { pagina += 1; dibujar(); });

  function filtrar() {
    const texto = $("#buscar").value.trim().toLowerCase();
    const tipo = $("#filtro-tipo").value, familia = $("#filtro-plataforma").value;
    const formato = $("#filtro-formato").value, tienda = $("#filtro-tienda").value;
    const soloOfertas = $("#solo-ofertas").checked;
    const lista = datos.juegos.filter((j) =>
      (!texto || j.titulo.toLowerCase().includes(texto)) &&
      (!tipo || j.tipo === tipo) &&
      (!familia || j.familias.includes(familia)) &&
      (!formato || j.formatos.includes(formato)) &&
      (!tienda || j.tiendas.includes(tienda)) &&
      (!soloOfertas || j.en_oferta));
    const orden = $("#orden").value;
    const comparar = {
      nombre: (a, b) => a.titulo.localeCompare(b.titulo, "es"),
      precio: (a, b) => a.precio - b.precio || a.titulo.localeCompare(b.titulo),
      descuento: (a, b) => b.descuento - a.descuento || a.precio - b.precio,
      calificacion: (a, b) => (b.metascore ?? -1) - (a.metascore ?? -1) || a.titulo.localeCompare(b.titulo),
    }[orden];
    return lista.sort(comparar);
  }

  function tarjeta(juego) {
    const imagen = urlSegura(juego.imagen);
    const enlace = "juego.html?clave=" + encodeURIComponent(juego.clave);
    const lineaPrecio = el("div", {}, el("span", { class: "precio", text: precio(juego.precio) }));
    if (juego.regular && juego.regular > juego.precio) lineaPrecio.append(el("span", { class: "tachado", text: precio(juego.regular) }));
    const etiquetas = el("div", { class: "chips" });
    if (juego.descuento > 0) etiquetas.append(el("span", { class: "etiqueta descuento", text: `-${juego.descuento}%` }));
    if (juego.minimo_historico) etiquetas.append(el("span", { class: "etiqueta minimo", text: "Mínimo histórico" }));
    if (juego.desactualizado) etiquetas.append(el("span", { class: "etiqueta viejo", text: "Precio desactualizado" }));
    const plataformas = el("div", { class: "chips" }, ...juego.plataformas.map((p) => el("span", { class: "chip", text: datos.plataformas[p] || p })));
    const calificacion = [];
    if (juego.metascore !== null) calificacion.push(`Metascore ${juego.metascore}`);
    if (juego.steam !== null) calificacion.push(`Steam ${juego.steam}%`);
    return el("article", { class: "card" },
      imagen ? el("a", { href: enlace }, el("img", { src: imagen, alt: "", loading: "lazy" })) : null,
      el("div", { class: "cuerpo" },
        el("h3", {}, el("a", { href: enlace, text: juego.titulo })),
        lineaPrecio, etiquetas, plataformas,
        el("div", { class: "nota", text: calificacion.join(" · ") || "Sin calificación" }),
        el("div", { class: "nota", text: `Mejor precio en ${datos.tiendas[juego.tienda] || juego.tienda} · ${juego.tiendas.length} tiendas` })));
  }

  function dibujar() {
    const lista = filtrar();
    const paginas = Math.max(1, Math.ceil(lista.length / POR_PAGINA));
    pagina = Math.min(Math.max(1, pagina), paginas);
    $("#resumen").textContent = `${lista.length} juegos (de ${datos.juegos.length} publicados con precio en 2 o más tiendas)`;
    $("#rejilla").replaceChildren(...lista.slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA).map(tarjeta));
    $("#pagina").textContent = `Página ${pagina} de ${paginas}`;
    $("#anterior").disabled = pagina <= 1;
    $("#siguiente").disabled = pagina >= paginas;
  }
  dibujar();
}

// ---------------------------------------------------------------------------------------------
// Gráfico de líneas en SVG (historial de precios y curvas de speedup)
// ---------------------------------------------------------------------------------------------

const COLORES = ["#2457d6", "#c62828", "#1b7f3b", "#b26a00", "#7b1fa2", "#00838f"];
const SVG = "http://www.w3.org/2000/svg";

function svg(etiqueta, atributos = {}, texto = null) {
  const nodo = document.createElementNS(SVG, etiqueta);
  for (const [k, v] of Object.entries(atributos)) nodo.setAttribute(k, v);
  if (texto !== null) nodo.textContent = texto;
  return nodo;
}

/** series: [{nombre, puntos: [[x, y], ...]}]. formatoY / formatoX convierten los valores en etiquetas. */
function graficoLineas(series, { formatoX = String, formatoY = String, ancho = 640, alto = 240 } = {}) {
  const todos = series.flatMap((s) => s.puntos);
  const contenedor = el("div");
  if (todos.length === 0) return contenedor;
  const xs = todos.map((p) => p[0]), ys = todos.map((p) => p[1]);
  let [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  if (x0 === x1) { x0 -= 1; x1 += 1; }
  if (y0 === y1) { y0 -= 1; y1 += 1; }
  const m = { izq: 60, der: 10, arr: 10, aba: 30 };
  const X = (x) => m.izq + ((x - x0) / (x1 - x0)) * (ancho - m.izq - m.der);
  const Y = (y) => alto - m.aba - ((y - y0) / (y1 - y0)) * (alto - m.arr - m.aba);
  const lienzo = svg("svg", { viewBox: `0 0 ${ancho} ${alto}`, class: "grafico", role: "img" });
  lienzo.append(svg("line", { x1: m.izq, y1: alto - m.aba, x2: ancho - m.der, y2: alto - m.aba, stroke: "currentColor", "stroke-opacity": ".3" }));
  lienzo.append(svg("text", { x: 4, y: Y(y1) + 4 }, formatoY(y1)), svg("text", { x: 4, y: Y(y0) + 4 }, formatoY(y0)));
  lienzo.append(svg("text", { x: m.izq, y: alto - 8 }, formatoX(x0)), svg("text", { x: ancho - m.der - 90, y: alto - 8 }, formatoX(x1)));
  const leyenda = el("div", { class: "leyenda" });
  series.forEach((serie, i) => {
    const color = COLORES[i % COLORES.length];
    const puntos = serie.puntos.map(([x, y]) => `${X(x).toFixed(1)},${Y(y).toFixed(1)}`).join(" ");
    lienzo.append(svg("polyline", { points: puntos, fill: "none", stroke: color, "stroke-width": 2 }));
    for (const [x, y] of serie.puntos) lienzo.append(svg("circle", { cx: X(x), cy: Y(y), r: 3, fill: color }));
    leyenda.append(el("span", { style: `color:${color}`, text: "● " + serie.nombre }));
  });
  contenedor.append(lienzo, leyenda);
  return contenedor;
}

function tabla(encabezados, filas, numericas = []) {
  return el("table", {},
    el("thead", {}, el("tr", {}, ...encabezados.map((h, i) => el("th", { class: numericas.includes(i) ? "num" : null, text: h })))),
    el("tbody", {}, ...filas.map((fila) => el("tr", {}, ...fila.map((celda, i) =>
      el("td", { class: numericas.includes(i) ? "num" : null }, celda instanceof Node ? celda : document.createTextNode(celda ?? "—")))))));
}

function enlaceExterno(url, texto) {
  const segura = urlSegura(url);
  return segura ? el("a", { href: segura, target: "_blank", rel: "noopener noreferrer nofollow", text: texto }) : document.createTextNode(texto);
}

// ---------------------------------------------------------------------------------------------
// Página de detalle
// ---------------------------------------------------------------------------------------------

async function paginaDetalle() {
  const contenido = $("#contenido");
  const clave = new URLSearchParams(location.search).get("clave") || "";
  if (!/^[a-z0-9-]+$/.test(clave)) { // Solo claves válidas: evita pedir rutas arbitrarias.
    contenido.replaceChildren(el("p", { class: "error", text: "Juego no válido." }));
    return;
  }
  let juego;
  try {
    juego = await cargar(`datos/juegos/${clave}.json`);
  } catch (error) {
    mostrarError(contenido, error);
    return;
  }
  document.title = juego.titulo + " · Radar de Ofertas";
  mostrarActualizacion(juego.generado_en);
  const imagen = urlSegura(juego.imagen);

  const precios = tabla(["Tienda", "Plataforma", "Formato", "Precio", "Regular", "Obtenido"],
    juego.precios.map((p) => [
      enlaceExterno(p.url, p.tienda), p.plataforma, p.formato === "fisico" ? "Físico" : "Digital",
      el("span", {}, el("b", { text: precio(p.precio) }), p.en_oferta ? el("span", { class: "etiqueta descuento", text: " oferta", style: "margin-left:6px" }) : null),
      precio(p.regular),
      el("span", {}, document.createTextNode(fecha(p.obtenido_en)), p.desactualizado ? el("span", { class: "etiqueta viejo", text: "desactualizado", style: "margin-left:6px" }) : null),
    ]), [3, 4]);

  const plataformas = tabla(["Plataforma", "Lanzamiento", "MSRP"],
    juego.plataformas.map((p) => [p.nombre, p.fecha_lanzamiento || "—", precio(p.msrp)]), [2]);
  const calificaciones = tabla(["Fuente", "Plataforma", "Puntaje", "Reseñas", "Obtenido"],
    juego.calificaciones.map((c) => [c.fuente, c.plataforma || "—", `${c.puntaje} / ${c.escala}`, c.resenas ?? "—", fecha(c.obtenido_en)]), [2, 3]);

  const series = juego.historial.map((h) => ({ nombre: h.tienda, puntos: h.puntos.map(([f, c]) => [Date.parse(f), c]) }));
  contenido.replaceChildren(
    el("div", { class: "detalle" },
      el("div", {}, imagen ? el("img", { src: imagen, alt: "" }) : null),
      el("div", {},
        el("h2", { text: juego.titulo }),
        el("p", { class: "nota", text: `Tipo: ${juego.tipo}` }),
        el("section", { class: "panel" }, el("h2", { text: "Precios (de menor a mayor)" }), precios),
        el("section", { class: "panel" }, el("h2", { text: "Historial de precios por tienda" }),
          series.length ? graficoLineas(series, { formatoX: (x) => new Date(x).toLocaleDateString("es-CR"), formatoY: precio }) : el("p", { class: "nota", text: "Sin historial." })),
        el("section", { class: "panel" }, el("h2", { text: "Plataformas y precio de referencia (MSRP)" }), plataformas),
        el("section", { class: "panel" }, el("h2", { text: "Calificaciones" }), calificaciones),
        el("section", { class: "panel" }, el("h2", { text: "Duración (How Long To Beat)" }),
          el("p", { class: "nota", text: juego.duracion_nota })))));
}

// ---------------------------------------------------------------------------------------------
// Panel de métricas
// ---------------------------------------------------------------------------------------------

async function paginaMetricas() {
  const contenido = $("#contenido");
  let m;
  try {
    m = await cargar("datos/metricas.json");
  } catch (error) {
    mostrarError(contenido, error);
    return;
  }
  mostrarActualizacion(m.generado_en);
  const secciones = [];
  const u = m.ultima_ejecucion;
  if (u) {
    secciones.push(el("section", { class: "panel" }, el("h2", { text: "Última ejecución" }),
      el("div", { class: "kpis" },
        ...[["Fecha", fecha(u.iniciada_en)], ["Duración", segundos(u.duracion_s)], ["Modo", u.modo],
            ["Datos", u.fuente_datos], ["Estado", u.estado], ["Juegos publicados", m.cobertura.publicados],
            ["Juegos activos", m.cobertura.activos], ["Con menos de 2 tiendas", m.cobertura.sin_precio_suficiente]]
          .map(([t, v]) => el("div", { class: "kpi" }, el("span", { class: "nota", text: t }), el("b", { text: String(v) }))))));
    secciones.push(el("section", { class: "panel" }, el("h2", { text: "Tiempo por etapa" }),
      tabla(["Etapa", "Elementos", "Tiempo ocupado", "Ventana"],
        m.etapas.map((e) => [e.etapa, e.elementos, segundos(e.ocupado_s), segundos(e.ventana_s)]), [1, 2, 3]),
      el("p", { class: "nota", text: "Tiempo ocupado: suma del trabajo de todos los workers de la etapa. Ventana: tiempo de reloj entre su primer y su último elemento." })));
    secciones.push(el("section", { class: "panel" }, el("h2", { text: "Solicitudes por sitio" }),
      tabla(["Sitio", "Exitosas", "Reintentadas", "Fallidas", "Desde caché", "Bloqueadas por robots.txt"],
        m.solicitudes.map((s) => [s.dominio, s.exitosas, s.reintentos, s.fallidas, s.desde_almacen, s.bloqueadas_robots]), [1, 2, 3, 4, 5])));
  } else {
    secciones.push(el("section", { class: "panel" }, el("p", { text: "Todavía no hay ejecuciones registradas." })));
  }
  secciones.push(el("section", { class: "panel" }, el("h2", { text: `Cola de fallidos (${m.fallidos.length})` }),
    m.fallidos.length ? tabla(["URL", "Error", "Resuelto en el reintento final"], m.fallidos.map((f) => [enlaceExterno(f.url, f.url), f.mensaje, f.resuelto ? "Sí" : "No"]))
      : el("p", { class: "nota", text: "Sin fallos en la última ejecución." })));
  if (m.errores && m.errores.length) {
    secciones.push(el("section", { class: "panel" }, el("h2", { text: `Errores por etapa (${m.errores.length})` }),
      tabla(["Etapa", "Juego", "Mensaje"], m.errores.map((e) => [e.etapa, e.clave, e.mensaje]))));
  }
  secciones.push(el("section", { class: "panel" }, el("h2", { text: `Emparejamientos dudosos (${m.dudosos.length})` }),
    m.dudosos.length ? tabla(["Juego", "Tienda", "Producto", "Similitud", "Motivo"],
      m.dudosos.map((d) => [d.juego, d.tienda, enlaceExterno(d.url, d.producto), d.similitud.toFixed(2), d.motivo]), [3])
      : el("p", { class: "nota", text: "Sin casos dudosos." })));
  secciones.push(el("section", { class: "panel" }, el("h2", { text: `Juegos sin emparejar en ninguna tienda (${m.sin_emparejar.length})` }),
    m.sin_emparejar.length ? el("p", { text: m.sin_emparejar.join(" · ") }) : el("p", { class: "nota", text: "Todos los juegos tienen al menos una tienda." })));

  const mediciones = el("section", { class: "panel" }, el("h2", { text: "Curvas de speedup (modo replay)" }));
  if (m.mediciones.length === 0) {
    mediciones.append(el("p", { class: "nota", text: "Aún no hay mediciones. Se cargan desde datos/mediciones/*.csv cuando el equipo ejecute los barridos." }));
  } else {
    for (const etapa of m.mediciones) {
      mediciones.append(el("h3", { text: etapa.etapa }),
        graficoLineas([{ nombre: "S_abs", puntos: etapa.puntos.map((p) => [p.p, p.s_abs]) },
                       { nombre: "S_rel", puntos: etapa.puntos.map((p) => [p.p, p.s_rel]) },
                       { nombre: "E", puntos: etapa.puntos.map((p) => [p.p, p.eficiencia]) }],
                      { formatoX: (x) => `${x} workers`, formatoY: (y) => y.toFixed(2) }));
    }
  }
  secciones.push(mediciones);
  secciones.push(el("section", { class: "panel" }, el("h2", { text: "Ejecuciones recientes" }),
    tabla(["Fecha", "Modo", "Datos", "Duración", "Estado"], m.historial.map((h) => [fecha(h.iniciada_en), h.modo, h.fuente_datos, segundos(h.duracion_s), h.estado]), [3])));
  contenido.replaceChildren(...secciones);
}

const paginas = { resultados: paginaResultados, detalle: paginaDetalle, metricas: paginaMetricas };
paginas[document.body.dataset.pagina]?.();
