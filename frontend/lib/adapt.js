// Derives the view model the screens need from a single contract package.

const NIVEL_ORDER = { critico: 0, bajo: 1, adecuado: 2 };
const COP = new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 });

export const formatCop = (value) => COP.format(value);

export function cellToLatLon(index, grid) {
  const col = index % grid.cols;
  const row = Math.floor(index / grid.cols);
  const [lat0, lon0] = grid.origen;
  const metersPerDegLon = 111320 * Math.cos((lat0 * Math.PI) / 180);
  return {
    lat: lat0 + ((row + 0.5) * grid.celda_m) / 110540,
    lon: lon0 + ((col + 0.5) * grid.celda_m) / metersPerDegLon,
  };
}

export function latLonToCell(lat, lon, grid) {
  const [lat0, lon0] = grid.origen;
  const metersPerDegLon = 111320 * Math.cos((lat0 * Math.PI) / 180);
  return {
    c: Math.floor(((lon - lon0) * metersPerDegLon) / grid.celda_m),
    r: Math.floor(((lat - lat0) * 110540) / grid.celda_m),
  };
}

function worstNivel(zona) {
  return Object.values(zona.nivel).sort((a, b) => NIVEL_ORDER[a] - NIVEL_ORDER[b])[0];
}

export function adapt(pkg) {
  const { plot, grid, zonas, receta, riesgos, estacional, puntos, descartados, next_sample: nextSample } = pkg;

  const insideCells = grid.mask.reduce((acc, m) => acc + m, 0);
  const uncertainCells = grid.mask.reduce(
    (acc, m, i) => acc + (m && grid.sigma[i] > grid.sigma_umbral ? 1 : 0),
    0,
  );

  const criticalArea = zonas
    .filter((z) => worstNivel(z) === 'critico')
    .reduce((acc, z) => acc + z.area_ha, 0);

  return {
    plot,
    grid,
    contorno: pkg.contorno,
    puntos,
    descartados,
    zonas: zonas.map((z) => ({ ...z, peor: worstNivel(z) })),
    receta,
    riesgos: riesgos.slice(0, 3),
    estacional,
    voz: pkg.voz,
    nextSample: nextSample && { ...nextSample, celda: latLonToCell(nextSample.punto[0], nextSample.punto[1], grid) },
    sampling: {
      total: puntos.length + descartados.length,
      valid: puntos.length,
      rejected: descartados.length,
      suspicious: puntos.filter((p) => p.sospechoso).length,
    },
    coverage: {
      insideCells,
      uncertainCells,
      uncertainPct: insideCells ? Math.round((uncertainCells / insideCells) * 100) : 0,
    },
    criticalAreaHa: Math.round(criticalArea * 1000) / 1000,
    criticalSharePct: plot.area_ha ? Math.round((criticalArea / plot.area_ha) * 1000) / 10 : 0,
    stale: pkg.generado
      ? (Date.now() - Date.parse(pkg.generado)) / 3600000 > pkg.ttl_horas
      : false,
    degradado: pkg.degradado,
    aviso: pkg.aviso,
    generado: pkg.generado,
  };
}
