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

/**
 * Portada elegida por su CALIDAD REAL, no solo por la fuente.
 *
 * `candidatas` = [{url, hd}] en orden de preferencia (Steam, Best Buy, Metacritic, Nintendo). `hd` es una versión
 * más grande de la misma imagen que se ofrece con srcset "2x": las pantallas normales (1x) no la descargan.
 *
 * Por qué no basta con el orden de las fuentes (medido el 2026-11-11):
 * - Algunas imágenes de Best Buy son fotos CUADRADAS del producto (caja chica, márgenes blancos, a veces de baja
 *   resolución): recortarlas corta la caja y encogerlas desperdicia el cuadro.
 * - Metacritic no tiene un tamaño fijo: para algunos juegos su "original" mide 1335x2160 y para otros 125x187.
 *
 * Regla: se prueba cada candidata y se acepta la primera que sea VERTICAL y tenga resolución suficiente para el
 * tamaño real de la tarjeta en esta pantalla (ancho CSS × devicePixelRatio). Si ninguna lo cumple, se muestra la
 * de MAYOR resolución que cargó (ya está en la caché del navegador, no se descarga de nuevo); si no es vertical,
 * se ve completa sobre un fondo desenfocado de la misma imagen, que llena el cuadro sin recortar ni estirar.
 * Termina siempre: el índice solo avanza y la lista es finita.
 */
// ancho / alto; una portada 2:3 vale 0,67. Hasta 0,82 se llena el cuadro recortando como mucho ~9 % por lado (mejor
// que dejar bandas); más ancha que eso (cuadrada o apaisada) va completa sobre el fondo desenfocado.
const PROPORCION_VERTICAL_MAXIMA = 0.82;
// "Suficiente" = al menos tantos píxeles de ancho como ocupa la tarjeta en la pantalla: nada se agranda. (Con 80 %
// se aceptaban imágenes de Metacritic de 192 px que, para juegos recientes, ya son ampliaciones de 125 px.)
const FRACCION_RESOLUCION_SUFICIENTE = 1.0;

function imagen(candidatas, atributos = {}) {
  const lista = (candidatas || [])
    .map((c) => (typeof c === "string" ? { url: c } : c))
    .map((c) => ({ url: urlSegura(c.url), hd: urlSegura(c.hd), soloVertical: Boolean(c.solo_vertical) }))
    .filter((c) => c.url);
  if (lista.length === 0) return null;
  const img = el("img", { ...atributos, decoding: "async" });
  let actual = 0;          // Índice de la candidata que se está probando.
  let hdProbada = false;   // Si la versión "hd" de la candidata actual ya se probó.
  let mejor = null;        // La de mayor resolución vista hasta ahora: {src, area, vertical}.
  let decidido = false;    // true cuando ya se eligió la imagen definitiva.

  const presentar = (vertical) => {
    decidido = true;
    img.classList.toggle("completa", !vertical);
    const marco = img.parentElement;
    if (!marco) return;
    marco.classList.toggle("con-fondo", !vertical);
    if (!vertical) marco.style.setProperty("--fondo", `url("${img.currentSrc}")`);
  };
  const probar = (indice) => {
    actual = indice;
    hdProbada = false;
    const c = lista[indice];
    // Con srcset, una pantalla de escala >= 2 pide directamente la "hd" y se ahorra un paso.
    if (c.hd) img.srcset = `${c.url} 1x, ${c.hd} 2x`;
    else img.removeAttribute("srcset");
    img.src = c.url;
  };
  // Si la candidata actual tiene versión "hd" que aún no se probó, la prueba (true); si no, devuelve false.
  const probarHd = () => {
    const c = lista[actual];
    if (!c.hd || hdProbada || img.currentSrc === c.hd) return false;
    hdProbada = true;
    img.removeAttribute("srcset");
    img.src = c.hd;
    return true;
  };
  const siguiente = () => {
    if (actual + 1 < lista.length) { probar(actual + 1); return; }
    if (!mejor) return; // Ninguna cargó: queda el espacio vacío de la tarjeta.
    if (img.currentSrc === mejor.src) { presentar(mejor.vertical); return; }
    decidido = true; // El próximo "load" es la imagen elegida.
    img.removeAttribute("srcset");
    img.src = mejor.src;
  };

  img.addEventListener("error", () => {
    if (decidido) return;
    if (img.currentSrc === lista[actual].hd) hdProbada = true; // Falló la "hd": no se vuelve a intentar.
    if (!probarHd()) siguiente();
  });
  img.addEventListener("load", () => {
    const ancho = img.naturalWidth, alto = img.naturalHeight;
    const vertical = ancho / alto <= PROPORCION_VERTICAL_MAXIMA;
    if (decidido) { presentar(vertical); return; }
    const necesario = FRACCION_RESOLUCION_SUFICIENTE * (img.parentElement?.clientWidth || 212) * devicePixelRatio;
    if (vertical && ancho >= necesario) { presentar(true); return; }
    // No sirve tal cual: se recuerda si es la de más resolución y se prueba su "hd" o la siguiente candidata.
    // (Una "hd" más chica que la normal, como el original de 125 px de algunos juegos en Metacritic, simplemente
    // no gana por área: no hace falta un caso especial.) Las marcadas "solo vertical" (fotos cuadradas de Best Buy,
    // a veces ampliadas) no compiten como respaldo si no son verticales: sus píxeles no reflejan su calidad.
    const descartable = lista[actual].soloVertical && !vertical;
    if (!descartable && (!mejor || ancho * alto > mejor.area)) mejor = { src: img.currentSrc, area: ancho * alto, vertical };
    if (!probarHd()) siguiente();
  });
  probar(0);
  return img;
}

// ---------------------------------------------------------------------------------------------
// Monedas: los precios se guardan en centavos de USD (ADR-005); colones y euros son solo una conversión al mostrar
// (ADR-012) con las tasas que publica el pipeline en datos/tipo_cambio.json. Sin ese archivo, solo hay USD.
// ---------------------------------------------------------------------------------------------

const MONEDAS = [["USD", "USD $", "Dólares"], ["CRC", "CRC ₡", "Colones"], ["EUR", "EUR €", "Euros"]];
const CLAVE_MONEDA = "radar.moneda";
let tipoCambio = null;  // { tasas: { CRC, EUR }, actualizado_en, atribucion } o null.
let moneda = "USD";     // Moneda en la que se muestran los precios ahora mismo.

const tasaDe = (codigo) => (codigo === "USD" ? 1 : tipoCambio?.tasas?.[codigo] ?? null);

/** Carga las tasas y la moneda global elegida antes (si sigue disponible). */
async function cargarTipoCambio() {
  try { tipoCambio = await cargar("datos/tipo_cambio.json"); } catch { tipoCambio = null; }
  let guardada = "USD";
  try { guardada = localStorage.getItem(CLAVE_MONEDA) || "USD"; } catch { /* Sin almacenamiento: USD. */ }
  moneda = tasaDe(guardada) ? guardada : "USD";
  mostrarAtribucion();
}

/** Centavos de USD -> centésimos de la moneda elegida (los gráficos convierten sus puntos con esto). */
const convertir = (centavosUSD) => centavosUSD * tasaDe(moneda);

/** Da formato a un monto YA convertido (en centésimos de la moneda elegida). */
function formatear(centesimos, { enteros = false } = {}) {
  const unidades = centesimos / 100;
  if (moneda === "USD") return "$" + (enteros ? Math.round(unidades) : unidades.toFixed(2));
  // Colones sin decimales (como en Costa Rica: "₡25 990"); euros con 2 ("€12,34").
  const decimales = enteros || moneda === "CRC" ? 0 : 2;
  const numero = new Intl.NumberFormat("es-CR", { minimumFractionDigits: decimales, maximumFractionDigits: decimales }).format(unidades);
  return (moneda === "CRC" ? "₡" : "€") + numero;
}

/** Precio en centavos de USD, mostrado en la moneda elegida. */
function precio(centavosUSD) {
  return centavosUSD === null || centavosUSD === undefined ? "—" : formatear(convertir(centavosUSD));
}

/** Botones USD / CRC / EUR. ``alCambiar`` decide qué pasa después (guardar o no, volver a dibujar). */
function selectorMoneda(alCambiar, etiqueta) {
  if (!tipoCambio) return null;
  const grupo = el("div", { class: "moneda", role: "group", "aria-label": etiqueta });
  const pintar = () => { for (const b of grupo.children) b.setAttribute("aria-pressed", String(b.dataset.moneda === moneda)); };
  for (const [codigo, texto, nombre] of MONEDAS) {
    const boton = el("button", { type: "button", text: texto, title: "Mostrar los precios en " + nombre.toLowerCase() });
    boton.dataset.moneda = codigo;
    boton.addEventListener("click", () => { moneda = codigo; pintar(); alCambiar(codigo); });
    grupo.append(boton);
  }
  pintar();
  return grupo;
}

/** Atribución que exige la fuente de las tasas, en el pie de las páginas que las usan. */
function mostrarAtribucion() {
  const destino = $("#atribucion");
  if (!destino || !tipoCambio) return;
  // En UTC, como la publica la fuente (a las 00:00 UTC; en Costa Rica aún sería el día anterior).
  const dia = new Date(tipoCambio.actualizado_en).toLocaleDateString("es-CR", { dateStyle: "medium", timeZone: "UTC" });
  destino.replaceChildren(
    document.createTextNode(` · Colones y euros: conversión aproximada con el tipo de cambio del ${dia} (`),
    enlaceExterno(tipoCambio.atribucion.url, tipoCambio.atribucion.texto), document.createTextNode(")"));
}

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
  await cargarTipoCambio();
  // Selector GLOBAL: se guarda en el navegador y es la moneda inicial de todas las páginas (también del detalle).
  const global = selectorMoneda((codigo) => {
    try { localStorage.setItem(CLAVE_MONEDA, codigo); } catch { /* Navegación privada: solo esta visita. */ }
    dibujar();
  }, "Moneda de los precios (todo el sitio)");
  if (global) $("#moneda-global").replaceChildren(global);

  for (const [codigo, nombre] of Object.entries(datos.familias)) {
    $("#filtro-plataforma").append(el("option", { value: codigo, text: nombre }));
  }
  for (const [codigo, nombre] of Object.entries(datos.tiendas)) {
    $("#filtro-tienda").append(el("option", { value: codigo, text: nombre }));
  }

  // Filtros recordados. Se guardan en la URL (al volver con "atrás" desde un juego, o al compartir el enlace,
  // se ve lo mismo) y en el navegador (el menú "Ofertas" abre index.html sin parámetros, y la última selección
  // queda como predeterminada para la próxima visita). La URL manda sobre lo guardado.
  const CONTROLES = { q: "#buscar", tipo: "#filtro-tipo", plataforma: "#filtro-plataforma", formato: "#filtro-formato",
                      tienda: "#filtro-tienda", ofertas: "#solo-ofertas", orden: "#orden" };
  const CLAVE_GUARDADO = "radar.filtros";
  // Valores predeterminados tomados del HTML, no del estado actual: al volver con "atrás" el navegador ya
  // rellenó algunos campos antes de que corra este código, y entonces se confundían con los predeterminados.
  const POR_DEFECTO = Object.fromEntries(Object.entries(CONTROLES).map(([k, s]) => [k, predeterminado($(s))]));
  let pagina = 1;

  function predeterminado(control) {
    if (control.type === "checkbox") return control.defaultChecked ? "1" : "";
    if (control.tagName === "SELECT") return ([...control.options].find((o) => o.defaultSelected) || control.options[0]).value;
    return control.defaultValue;
  }
  function valorDe(control) { return control.type === "checkbox" ? (control.checked ? "1" : "") : control.value; }
  function poner(control, valor) {
    if (control.type === "checkbox") { control.checked = valor === "1"; return; }
    // Solo valores que existen (p. ej. una tienda que ya no tiene juegos publicados se ignora).
    if (control.tagName === "SELECT" && ![...control.options].some((o) => o.value === valor)) return;
    control.value = valor;
  }
  function restaurar() {
    let estado = Object.fromEntries(new URLSearchParams(location.search));
    if (Object.keys(estado).length === 0) {
      try { estado = JSON.parse(localStorage.getItem(CLAVE_GUARDADO)) || {}; } catch { estado = {}; }
    }
    // TODOS los campos se fijan (lo que no está guardado vuelve al predeterminado), así no queda nada que el
    // navegador haya rellenado por su cuenta.
    for (const [clave, selector] of Object.entries(CONTROLES)) {
      poner($(selector), POR_DEFECTO[clave]);
      if (typeof estado[clave] === "string") poner($(selector), estado[clave]);
    }
    pagina = Math.max(1, parseInt(estado.pagina, 10) || 1);
  }
  function guardar() {
    const estado = {};
    for (const [clave, selector] of Object.entries(CONTROLES)) {
      const valor = valorDe($(selector));
      if (valor !== POR_DEFECTO[clave]) estado[clave] = valor;  // Solo lo que cambia: URLs cortas.
    }
    if (pagina > 1) estado.pagina = String(pagina);
    const consulta = new URLSearchParams(estado).toString();
    history.replaceState(null, "", consulta ? "?" + consulta : location.pathname);
    try { localStorage.setItem(CLAVE_GUARDADO, JSON.stringify(estado)); } catch { /* Navegación privada: solo URL. */ }
  }

  restaurar();
  for (const selector of Object.values(CONTROLES)) {
    $(selector).addEventListener("input", () => { pagina = 1; dibujar(); });
  }
  $("#anterior").addEventListener("click", () => { pagina -= 1; dibujar(); });
  $("#siguiente").addEventListener("click", () => { pagina += 1; dibujar(); });
  $("#limpiar").addEventListener("click", () => {
    for (const [clave, selector] of Object.entries(CONTROLES)) poner($(selector), POR_DEFECTO[clave]);
    pagina = 1;
    dibujar();
  });

  function filtrar() {
    const texto = $("#buscar").value.trim().toLowerCase();
    const tipo = $("#filtro-tipo").value, familia = $("#filtro-plataforma").value;
    const formato = $("#filtro-formato").value, tienda = $("#filtro-tienda").value;
    const soloOfertas = $("#solo-ofertas").checked;
    // Cada OFERTA (producto con precio) debe cumplir TODOS los filtros a la vez. Antes cada filtro se comparaba
    // con las listas de todo el juego: "PC + Físico" aceptaba un juego de PC que solo era físico en PS5, y lo mismo
    // pasaba con plataforma + tienda, formato + tienda, tipo y "solo en oferta".
    const cumple = (o) =>
      (!tipo || o.tipo === tipo) && (!familia || o.familia === familia) && (!formato || o.formato === formato) &&
      (!tienda || o.tienda === tienda) && (!soloOfertas || o.en_oferta);
    const lista = [];
    for (const j of datos.juegos) {
      if (texto && !j.titulo.toLowerCase().includes(texto)) continue;
      const validas = j.ofertas.filter(cumple);  // Ya vienen de menor a mayor precio (generar.py).
      if (validas.length === 0) continue;
      // La tarjeta muestra la mejor oferta QUE CUMPLE el filtro (con "Nintendo" no se ve el precio de Steam).
      lista.push({ juego: j, mejor: validas[0], tiendas: new Set(validas.map((o) => o.tienda)).size });
    }
    const orden = $("#orden").value;
    const nombre = (a, b) => a.juego.titulo.localeCompare(b.juego.titulo, "es");
    const comparar = {
      nombre,
      precio: (a, b) => a.mejor.precio - b.mejor.precio || nombre(a, b),
      descuento: (a, b) => b.mejor.descuento - a.mejor.descuento || a.mejor.precio - b.mejor.precio || nombre(a, b),
      calificacion: (a, b) => (b.juego.metascore ?? -1) - (a.juego.metascore ?? -1) || nombre(a, b),
    }[orden];
    return lista.sort(comparar);
  }

  function tarjeta({ juego, mejor, tiendas }) {
    const portada = imagen(juego.imagenes, { alt: "", loading: "lazy" });
    const enlace = "juego.html?clave=" + encodeURIComponent(juego.clave);
    const lineaPrecio = el("div", {}, el("span", { class: "precio", text: precio(mejor.precio) }));
    if (mejor.regular && mejor.regular > mejor.precio) lineaPrecio.append(el("span", { class: "tachado", text: precio(mejor.regular) }));
    const etiquetas = el("div", { class: "chips" });
    if (mejor.descuento > 0) etiquetas.append(el("span", { class: "etiqueta descuento", text: `-${mejor.descuento}%` }));
    if (mejor.minimo_historico) etiquetas.append(el("span", { class: "etiqueta minimo", text: "Mínimo histórico" }));
    // La marca va con el precio que se muestra; el detalle del juego marca cada tienda por separado.
    if (mejor.desactualizado) etiquetas.append(el("span", { class: "etiqueta viejo", text: "Precio desactualizado" }));
    const plataformas = el("div", { class: "chips" }, ...juego.plataformas.map((p) => el("span", { class: "chip", text: datos.plataformas[p] || p })));
    const calificacion = [];
    if (juego.metascore !== null) calificacion.push(`Metascore ${juego.metascore}`);
    if (juego.steam !== null) calificacion.push(`Steam ${juego.steam}%`);
    return el("article", { class: "card" },
      portada ? el("a", { href: enlace, class: "portada" }, portada) : el("div", { class: "portada" }),
      el("div", { class: "cuerpo" },
        el("h3", {}, el("a", { href: enlace, text: juego.titulo })),
        lineaPrecio, etiquetas, plataformas,
        el("div", { class: "nota", text: calificacion.join(" · ") || "Sin calificación" }),
        el("div", { class: "nota", text: `Mejor precio en ${datos.tiendas[mejor.tienda] || mejor.tienda} · ${tiendas} ${tiendas === 1 ? "tienda" : "tiendas"}` })));
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
    guardar();
  }
  dibujar();
}

// ---------------------------------------------------------------------------------------------
// Gráfico de líneas en SVG (historial de precios y curvas de speedup)
// ---------------------------------------------------------------------------------------------

// 10 colores distinguibles entre sí y legibles sobre fondo claro y oscuro. Antes eran 6: con más tiendas en un
// mismo gráfico, dos líneas compartían color y no se podían diferenciar.
const COLORES = ["#3b6fe0", "#d64545", "#2e9e5b", "#e08a00", "#9b59d0", "#0fa3b1",
                 "#e05aa8", "#8a9a2b", "#7f8c8d", "#c1662f"];
const SVG = "http://www.w3.org/2000/svg";

function svg(etiqueta, atributos = {}, texto = null) {
  const nodo = document.createElementNS(SVG, etiqueta);
  for (const [k, v] of Object.entries(atributos)) nodo.setAttribute(k, v);
  if (texto !== null) nodo.textContent = texto;
  return nodo;
}

/**
 * Marcas "redondas" para un eje: entre min y max, unas `cantidad` marcas con paso 1, 2, 2,5 o 5 × 10^k
 * (p. ej. 20, 30, 40, 50 en vez de 24,99 y 52,99). El rango final se amplía hasta la marca redonda más cercana,
 * así los puntos nunca quedan pegados al borde.
 */
function marcasRedondas(min, max, cantidad = 5) {
  if (min === max) { const margen = Math.abs(min) * 0.1 || 1; min -= margen; max += margen; }
  const crudo = (max - min) / (cantidad - 1);
  const potencia = 10 ** Math.floor(Math.log10(crudo));
  const paso = [1, 2, 2.5, 5, 10].map((m) => m * potencia).find((p) => p >= crudo);
  const marcas = [];
  for (let v = Math.floor(min / paso) * paso; v <= Math.ceil(max / paso) * paso + paso / 1e6; v += paso) {
    marcas.push(Number(v.toFixed(10)));
  }
  return marcas;
}

/**
 * Gráfico de líneas en SVG.
 * series: [{nombre, puntos: [[x, y], ...]}].
 * - escalonado: el valor se mantiene hasta el siguiente punto (así se comportan los precios: un precio dura hasta
 *   que cambia). Con líneas rectas parecería que el precio bajó "poco a poco" entre dos días.
 * - escalaX: "lineal" o "log2" (para workers 1, 2, 4… 64: con escala lineal se amontonan a la izquierda).
 * Cada punto tiene un <title>: al pasar el mouse se ve la serie, el valor de x y el de y.
 */
function graficoLineas(series, { formatoX = String, formatoY = String, escalonado = false, escalaX = "lineal",
                                 ancho = 640, alto = 260 } = {}) {
  const todos = series.flatMap((s) => s.puntos);
  const contenedor = el("div");
  if (todos.length === 0) return contenedor;
  const fx = escalaX === "log2" ? (x) => Math.log2(x) : (x) => x;
  const xsUnicos = [...new Set(todos.map((p) => p[0]))].sort((a, b) => a - b);
  const marcasY = marcasRedondas(Math.min(...todos.map((p) => p[1])), Math.max(...todos.map((p) => p[1])));
  const [y0, y1] = [marcasY[0], marcasY[marcasY.length - 1]];
  let [x0, x1] = [fx(xsUnicos[0]), fx(xsUnicos[xsUnicos.length - 1])];
  if (x0 === x1) { x0 -= 1; x1 += 1; }
  const m = { izq: 70, der: 20, arr: 14, aba: 38 };
  const X = (x) => m.izq + ((fx(x) - x0) / (x1 - x0)) * (ancho - m.izq - m.der);
  const Y = (y) => alto - m.aba - ((y - y0) / (y1 - y0)) * (alto - m.arr - m.aba);
  const lienzo = svg("svg", { viewBox: `0 0 ${ancho} ${alto}`, class: "grafico", role: "img" });

  // Eje Y: líneas guía horizontales con su valor.
  for (const marca of marcasY) {
    lienzo.append(
      svg("line", { x1: m.izq, x2: ancho - m.der, y1: Y(marca), y2: Y(marca), stroke: "currentColor",
                    "stroke-opacity": marca === y0 ? ".4" : ".12" }),
      svg("text", { x: m.izq - 8, y: Y(marca) + 4, "text-anchor": "end" }, formatoY(marca)));
  }
  // Eje X: una marca por cada valor con datos (como máximo ~7, repartidas para que no se encimen).
  const cada = Math.ceil(xsUnicos.length / 7);
  xsUnicos.forEach((x, i) => {
    if (i % cada !== 0 && i !== xsUnicos.length - 1) return;
    lienzo.append(
      svg("line", { x1: X(x), x2: X(x), y1: alto - m.aba, y2: alto - m.aba + 5, stroke: "currentColor", "stroke-opacity": ".4" }),
      svg("text", { x: X(x), y: alto - m.aba + 20, "text-anchor": "middle" }, formatoX(x)));
  });

  const leyenda = el("div", { class: "leyenda" });
  const xFinal = xsUnicos[xsUnicos.length - 1];
  series.forEach((serie, i) => {
    const color = COLORES[i % COLORES.length];
    const puntos = [...serie.puntos].sort((a, b) => a[0] - b[0]);
    let trazo = "";
    puntos.forEach(([x, y], k) => {
      if (k === 0) trazo += `M${X(x).toFixed(1)},${Y(y).toFixed(1)}`;
      else trazo += escalonado ? `H${X(x).toFixed(1)}V${Y(y).toFixed(1)}` : `L${X(x).toFixed(1)},${Y(y).toFixed(1)}`;
    });
    // Escalonado: el último precio conocido sigue vigente hasta el último día del gráfico.
    if (escalonado && puntos.length && puntos[puntos.length - 1][0] !== xFinal) trazo += `H${X(xFinal).toFixed(1)}`;
    lienzo.append(svg("path", { d: trazo, fill: "none", stroke: color, "stroke-width": 2.5, "stroke-linejoin": "round" }));
    for (const [x, y] of puntos) {
      const punto = svg("circle", { cx: X(x), cy: Y(y), r: 4.5, fill: color });
      punto.append(svg("title", {}, `${serie.nombre}\n${formatoX(x)}: ${formatoY(y)}`));
      lienzo.append(punto);
    }
    leyenda.append(el("span", { style: `color:${color}`, text: "● " + serie.nombre }));
  });
  contenedor.append(lienzo, leyenda);
  return contenedor;
}

// ---------------------------------------------------------------------------------------------
// Gráfico del historial de precios (diseño inspirado en DekuDeals)
// ---------------------------------------------------------------------------------------------

const MESES_INICIAL = ["E", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
const DIA_MS = 86400000;

/**
 * Historial de precios con eje de TIEMPO continuo.
 * - Líneas escalonadas finas y sin puntos: un precio vale hasta que cambia; cada línea se extiende hasta el último
 *   día del gráfico (su último precio sigue vigente).
 * - Eje X: una línea guía por mes con su inicial y el año en enero; si el período dura menos de ~2 meses, una
 *   guía por semana con el día.
 * - Eje Y: valores redondos escritos dentro del área, sobre líneas guía tenues.
 * - Al pasar el mouse: línea vertical y recuadro con el precio de cada tienda ese día (de menor a mayor).
 * series: [{nombre, puntos: [[milisegundos UTC del día, centavos], ...]}]
 */
function graficoHistorial(series, { ancho = 720, alto = 300 } = {}) {
  const todos = series.flatMap((s) => s.puntos);
  const contenedor = el("div", { class: "grafico-historial" });
  if (todos.length === 0) return contenedor;
  const tiempos = todos.map((p) => p[0]);
  const t0 = Math.min(...tiempos), t1 = Math.max(Math.max(...tiempos), t0 + DIA_MS);
  const marcasY = marcasRedondas(Math.min(...todos.map((p) => p[1])), Math.max(...todos.map((p) => p[1])));
  const [y0, y1] = [marcasY[0], marcasY[marcasY.length - 1]];
  const m = { izq: 6, der: 6, arr: 10, aba: 30 };
  const X = (t) => m.izq + ((t - t0) / (t1 - t0)) * (ancho - m.izq - m.der);
  const Y = (v) => alto - m.aba - ((v - y0) / (y1 - y0)) * (alto - m.arr - m.aba);
  const lienzo = svg("svg", { viewBox: `0 0 ${ancho} ${alto}`, class: "grafico", role: "img",
                               "aria-label": "Historial de precios por tienda" });
  lienzo.append(svg("rect", { x: m.izq, y: m.arr, width: ancho - m.izq - m.der, height: alto - m.arr - m.aba, class: "area" }));

  // Guías verticales: por mes (inicial del mes; el año en enero) o, en períodos cortos, por semana.
  const fechaUTC = (t) => new Date(t);
  const guias = [];
  if (t1 - t0 > 60 * DIA_MS) {
    const d = fechaUTC(t0);
    let cursor = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1);
    while (cursor <= t1) {
      const f = fechaUTC(cursor);
      guias.push({ t: cursor, texto: f.getUTCMonth() === 0 ? String(f.getUTCFullYear()) : MESES_INICIAL[f.getUTCMonth()],
                   fuerte: f.getUTCMonth() === 0 });
      cursor = Date.UTC(f.getUTCFullYear(), f.getUTCMonth() + 1, 1);
    }
  } else {
    for (let t = t0; t <= t1; t += 7 * DIA_MS) {
      guias.push({ t, texto: fechaUTC(t).toLocaleDateString("es-CR", { timeZone: "UTC", day: "numeric", month: "short" }) });
    }
  }
  for (const g of guias) {
    lienzo.append(
      svg("line", { x1: X(g.t), x2: X(g.t), y1: m.arr, y2: alto - m.aba, class: g.fuerte ? "guia fuerte" : "guia" }),
      svg("text", { x: X(g.t), y: alto - 10, "text-anchor": "middle", class: g.fuerte ? "eje fuerte" : "eje" }, g.texto));
  }
  // Guías horizontales con el valor escrito dentro del área, arriba de la línea. Si todas las marcas caen en
  // dólares enteros se escriben así ("$20"); si no (juegos baratos, pasos de 50 centavos), con centavos ("$2.50").
  // Antes siempre se redondeaba al dólar y aparecían etiquetas repetidas ("$1", "$1", "$2"…).
  // Los puntos ya vienen convertidos a la moneda elegida (paginaDetalle): aquí solo se da formato.
  const enUnidadesEnteras = marcasY.every((v) => Math.abs(v % 100) < 1e-6);
  const etiquetaY = (v) => formatear(v, { enteros: enUnidadesEnteras });
  for (const v of marcasY) {
    lienzo.append(svg("line", { x1: m.izq, x2: ancho - m.der, y1: Y(v), y2: Y(v), class: "guia" }));
    // El valor va arriba de su línea; el de la línea superior, debajo (si no, quedaría cortado por el borde).
    if (v !== y0) lienzo.append(svg("text", { x: m.izq + 6, y: v === y1 ? Y(v) + 15 : Y(v) - 5, class: "eje" }, etiquetaY(v)));
  }

  // Líneas escalonadas (finas, sin puntos), extendidas hasta el último día.
  const ordenadas = series.map((s, i) => ({ ...s, color: COLORES[i % COLORES.length],
                                            puntos: [...s.puntos].sort((a, b) => a[0] - b[0]) }));
  for (const s of ordenadas) {
    let trazo = "";
    s.puntos.forEach(([t, v], k) => {
      trazo += k === 0 ? `M${X(t).toFixed(1)},${Y(v).toFixed(1)}` : `H${X(t).toFixed(1)}V${Y(v).toFixed(1)}`;
    });
    trazo += `H${X(t1).toFixed(1)}`;
    lienzo.append(svg("path", { d: trazo, fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "miter" }));
  }

  // Interacción: línea vertical + recuadro con el precio de cada tienda ese día.
  const cursor = svg("line", { y1: m.arr, y2: alto - m.aba, class: "cursor", visibility: "hidden" });
  const capa = svg("rect", { x: m.izq, y: m.arr, width: ancho - m.izq - m.der, height: alto - m.arr - m.aba, fill: "transparent" });
  lienzo.append(cursor, capa);
  const recuadro = el("div", { class: "recuadro", hidden: "" });
  const precioEn = (s, t) => { let v = null; for (const [tp, vp] of s.puntos) { if (tp <= t) v = vp; else break; } return v; };
  capa.addEventListener("mousemove", (evento) => {
    const caja = lienzo.getBoundingClientRect();
    const x = ((evento.clientX - caja.left) / caja.width) * ancho;
    const t = Math.round((t0 + ((x - m.izq) / (ancho - m.izq - m.der)) * (t1 - t0)) / DIA_MS) * DIA_MS;
    cursor.setAttribute("x1", X(t)); cursor.setAttribute("x2", X(t)); cursor.setAttribute("visibility", "visible");
    const filas = ordenadas.map((s) => ({ s, v: precioEn(s, t) })).filter((f) => f.v !== null).sort((a, b) => a.v - b.v);
    recuadro.replaceChildren(
      el("b", { text: fechaUTC(t).toLocaleDateString("es-CR", { timeZone: "UTC", day: "numeric", month: "short", year: "numeric" }) }),
      ...filas.map((f) => el("div", {}, el("span", { style: `color:${f.s.color}`, text: "● " }),
                                       document.createTextNode(`${formatear(f.v)} · ${f.s.nombre}`))));
    recuadro.hidden = false;
    const izquierda = evento.clientX - contenedor.getBoundingClientRect().left;
    recuadro.style.left = `${Math.min(izquierda + 12, contenedor.clientWidth - recuadro.offsetWidth - 4)}px`;
  });
  capa.addEventListener("mouseleave", () => { recuadro.hidden = true; cursor.setAttribute("visibility", "hidden"); });

  const leyenda = el("div", { class: "leyenda" },
    ...ordenadas.map((s) => el("span", { style: `color:${s.color}`, text: "● " + s.nombre })));
  contenedor.append(lienzo, recuadro, leyenda);
  return contenedor;
}

/** Resumen "Mínimo histórico" por formato, como encabezado del historial. */
function resumenMinimos(minimos) {
  const formatos = [["digital", "Digital"], ["fisico", "Físico"]].filter(([clave]) => minimos?.[clave]);
  if (formatos.length === 0) return null;
  return el("div", { class: "minimos" },
    el("div", { class: "minimos-titulo", text: "Mínimo histórico" }),
    el("div", { class: "minimos-columnas" },
      ...formatos.map(([clave, nombre]) => {
        const dato = minimos[clave];
        return el("div", {},
          el("div", { class: "nota", text: nombre }),
          el("div", {}, el("b", { text: precio(dato.precio) }),
             dato.descuento > 0 ? el("span", { class: "nota", text: ` (-${dato.descuento}%)` }) : null));
      })));
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

const NOMBRES_TIPO = { juego: "Juego", juego_dlc: "Juego + DLC", dlc: "DLC", otro: "Otro (paquete)" };

/** Botón "Volver a ofertas". Si se llegó desde la página de ofertas, vuelve atrás en el historial: así se conserva
 *  la página de resultados y la posición en la que estaba. Si se entró directo (un enlace compartido), abre la página
 *  de ofertas, que igual recuerda los filtros guardados. */
function botonVolver() {
  const boton = el("a", { href: "index.html", class: "volver", text: "← Volver a ofertas" });
  boton.addEventListener("click", (evento) => {
    let desdeOfertas = false;
    try {
      const anterior = new URL(document.referrer);
      desdeOfertas = anterior.origin === location.origin && /\/(index\.html)?$/.test(anterior.pathname);
    } catch { /* Sin página anterior. */ }
    if (desdeOfertas && history.length > 1) { evento.preventDefault(); history.back(); }
  });
  return boton;
}

async function paginaDetalle() {
  const contenido = $("#contenido");
  const clave = new URLSearchParams(location.search).get("clave") || "";
  if (!/^[a-z0-9-]+$/.test(clave)) { // Solo claves válidas: evita pedir rutas arbitrarias.
    contenido.replaceChildren(botonVolver(), el("p", { class: "error", text: "Juego no válido." }));
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
  await cargarTipoCambio();  // Empieza con la moneda global elegida en la página de ofertas.
  // La portada se crea una sola vez: al cambiar de moneda se vuelve a dibujar todo lo demás sin recargarla.
  const portada = imagen(juego.imagenes, { alt: "Portada de " + juego.titulo });

  function dibujar() {
    // Selector LOCAL: cambia la moneda solo en esta página; no se guarda (la global sigue igual).
    const local = selectorMoneda(() => dibujar(), "Moneda de los precios (solo esta página)");
    const aviso = moneda === "USD" ? null : el("p", { class: "nota",
      text: "Precios convertidos desde USD con el tipo de cambio del día; las tiendas cobran en USD, así que el monto final puede variar." });

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

    // Un punto por tienda y por día ("AAAA-MM-DD", día UTC). Date.parse lo interpreta como medianoche UTC, por eso
    // la etiqueta también se formatea en UTC (si no, en Costa Rica mostraría el día anterior). Los precios se
    // convierten aquí a la moneda elegida, así las marcas del eje quedan redondas en esa moneda.
    const series = juego.historial.map((h) => ({ nombre: h.tienda, puntos: h.puntos.map(([dia, c]) => [Date.parse(dia), convertir(c)]) }));
    const dias = new Set(series.flatMap((s) => s.puntos.map((p) => p[0])));
    const diaCorto = (x) => new Date(x).toLocaleDateString("es-CR", { timeZone: "UTC", day: "numeric", month: "short" });
    // Con un solo día no hay tendencia que mostrar: un gráfico ahí solo confundiría (puntos sueltos sin líneas).
    const historial = dias.size >= 2
      ? graficoHistorial(series)
      : el("p", { class: "nota", text: dias.size === 1
          ? `El historial se está construyendo: por ahora hay precios de un solo día (${diaCorto([...dias][0])}). `
            + "El sitio guarda los precios de cada actualización diaria; el gráfico aparecerá cuando haya al menos dos días."
          : "Sin historial de precios." });
    contenido.replaceChildren(
      botonVolver(),
      el("div", { class: "detalle" },
        el("div", { class: "portada" }, portada),
        el("div", {},
          el("h2", { text: juego.titulo }),
          el("p", { class: "nota", text: `Tipo: ${NOMBRES_TIPO[juego.tipo] || juego.tipo}` }),
          el("section", { class: "panel" },
            el("div", { class: "panel-cabecera" }, el("h2", { text: "Precios (de menor a mayor)" }), local),
            aviso, precios),
          el("section", { class: "panel" }, el("h2", { text: "Historial de precios" }), resumenMinimos(juego.minimos), historial),
          el("section", { class: "panel" }, el("h2", { text: "Plataformas y precio de referencia (MSRP)" }), plataformas),
          el("section", { class: "panel" }, el("h2", { text: "Calificaciones" }), calificaciones),
          el("section", { class: "panel" }, el("h2", { text: "Duración (How Long To Beat)" }),
            el("p", { class: "nota", text: juego.duracion_nota })))));
  }
  dibujar();
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
  secciones.push(el("section", { class: "panel" }, el("h2", { text: `Emparejamientos dudosos y ediciones (${m.dudosos.length})` }),
    el("p", { class: "nota", text: "Dudoso: no se publica su precio. Publicado (edición): la tienda vende una edición con contenido extra (GOTY, Complete…) y se muestra como Juego + DLC." }),
    m.dudosos.length ? tabla(["Juego", "Tienda", "Producto", "Similitud", "Estado", "Motivo"],
      m.dudosos.map((d) => [d.juego, d.tienda, enlaceExterno(d.url, d.producto), d.similitud.toFixed(2), d.estado, d.motivo]), [3])
      : el("p", { class: "nota", text: "Sin casos dudosos." })));
  // Lista numerada en orden alfabético, en columnas, con un buscador: antes era un solo párrafo con todos los
  // títulos separados por "·" (más de 300), imposible de leer.
  const sinEmparejar = [...m.sin_emparejar]
    .map((j) => (typeof j === "string" ? { titulo: j, plataformas: [] } : j))  // Formato anterior: solo el título.
    .sort((a, b) => a.titulo.localeCompare(b.titulo, "es", { sensitivity: "base" }));
  const seccionSinEmparejar = el("section", { class: "panel" },
    el("h2", { text: `Juegos sin emparejar en ninguna tienda (${sinEmparejar.length})` }),
    el("p", { class: "nota", text: "Juegos del catálogo para los que ninguna tienda tiene un producto aceptado (no se publican). Entre paréntesis, las plataformas en las que se buscaron." }));
  if (sinEmparejar.length) {
    const buscador = el("input", { type: "search", placeholder: "Buscar en la lista…", class: "buscador-lista", "aria-label": "Buscar juegos sin emparejar" });
    const lista = el("ol", { class: "lista-columnas" }, ...sinEmparejar.map((j) =>
      el("li", {}, document.createTextNode(j.titulo),
        j.plataformas.length ? el("span", { class: "nota", text: ` (${j.plataformas.join(", ")})` }) : null)));
    buscador.addEventListener("input", () => {
      const texto = buscador.value.trim().toLowerCase();
      for (const item of lista.children) item.hidden = Boolean(texto) && !item.textContent.toLowerCase().includes(texto);
    });
    seccionSinEmparejar.append(buscador, lista);
  } else {
    seccionSinEmparejar.append(el("p", { class: "nota", text: "Todos los juegos tienen al menos una tienda." }));
  }
  secciones.push(seccionSinEmparejar);

  const mediciones = el("section", { class: "panel" }, el("h2", { text: "Curvas de speedup (modo replay)" }));
  if (m.mediciones.length === 0) {
    mediciones.append(el("p", { class: "nota", text: "Aún no hay mediciones. Se cargan desde datos/mediciones/*.csv cuando el equipo ejecute los barridos." }));
  } else {
    for (const etapa of m.mediciones) {
      mediciones.append(el("h3", { text: etapa.etapa }),
        graficoLineas([{ nombre: "S_abs", puntos: etapa.puntos.map((p) => [p.p, p.s_abs]) },
                       { nombre: "S_rel", puntos: etapa.puntos.map((p) => [p.p, p.s_rel]) },
                       { nombre: "E", puntos: etapa.puntos.map((p) => [p.p, p.eficiencia]) }],
                      // Workers 1, 2, 4… 64: escala logarítmica para que no se amontonen a la izquierda.
                      { formatoX: (x) => `${x}`, formatoY: (y) => y.toFixed(2), escalaX: "log2" }));
    }
  }
  secciones.push(mediciones);
  secciones.push(el("section", { class: "panel" }, el("h2", { text: "Ejecuciones recientes" }),
    tabla(["Fecha", "Modo", "Datos", "Duración", "Estado"], m.historial.map((h) => [fecha(h.iniciada_en), h.modo, h.fuente_datos, segundos(h.duracion_s), h.estado]), [3])));
  contenido.replaceChildren(...secciones);
}

// ---------------------------------------------------------------------------------------------
// Tema claro / oscuro
// ---------------------------------------------------------------------------------------------

// Sin elección se sigue al sistema. El botón fija "light" o "dark" en <html data-theme> y lo guarda en el
// navegador; el <script> del <head> de cada página lo aplica antes de pintar en las siguientes visitas.
function iniciarTema() {
  const boton = $("#tema");
  if (!boton) return;
  const sistemaOscuro = matchMedia("(prefers-color-scheme: dark)");
  const actual = () => document.documentElement.dataset.theme || (sistemaOscuro.matches ? "dark" : "light");
  const rotular = () => {
    const oscuro = actual() === "dark";
    boton.textContent = oscuro ? "Modo claro" : "Modo oscuro";  // El botón dice a qué modo cambia.
    boton.title = oscuro ? "Cambiar a modo claro" : "Cambiar a modo oscuro";
  };
  boton.addEventListener("click", () => {
    const nuevo = actual() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = nuevo;
    try { localStorage.setItem("radar.tema", nuevo); } catch { /* Navegación privada: vale solo esta página. */ }
    rotular();
  });
  sistemaOscuro.addEventListener("change", rotular);
  rotular();
}
iniciarTema();

const paginas = { resultados: paginaResultados, detalle: paginaDetalle, metricas: paginaMetricas };
paginas[document.body.dataset.pagina]?.();
