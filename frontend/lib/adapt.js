// Derives the view model the screens need from a contract v2 package.

const NIVEL_ORDER = { critico: 0, bajo: 1, adecuado: 2 };
const NUTRIENTS = ['N', 'P', 'K'];

export const CONTRACT_VERSION = '2.0';

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

// Availability against the profile requirement. The cuts are ratios, not invented
// percentage thresholds: below half the requirement is critical, below it is low.
function nivelFromRatio(ratio) {
  if (ratio < 0.5) return 'critico';
  if (ratio < 1) return 'bajo';
  return 'adecuado';
}

function zoneLevels(assessment) {
  if (!assessment) return null;
  const available = assessment.estimated_crop_available;
  const required = assessment.crop_requirement;
  if (!available || !required) return null;
  return Object.fromEntries(NUTRIENTS.map((n) => {
    const need = required[n];
    return [n, need ? nivelFromRatio(available[n] / need) : 'adecuado'];
  }));
}

function worstNivel(levels) {
  if (!levels) return 'adecuado';
  return Object.values(levels).sort((a, b) => NIVEL_ORDER[a] - NIVEL_ORDER[b])[0];
}

function adaptGrid(spatialGrid) {
  const nutrients = spatialGrid.nutrients || {};
  const uncertainty = spatialGrid.combined_uncertainty || {};
  const grid = {
    cols: spatialGrid.cols,
    rows: spatialGrid.rows,
    celda_m: spatialGrid.cell_size?.value,
    origen: [spatialGrid.origin?.latitude, spatialGrid.origin?.longitude],
    mask: spatialGrid.mask,
    sigma: uncertainty.values || [],
    sigma_umbral: uncertainty.threshold,
    sigma_metodo: uncertainty.threshold_method,
    sigma_unidad: uncertainty.unit,
    unidad: nutrients.N?.unit,
    base: nutrients.N?.basis,
  };
  for (const n of NUTRIENTS) {
    grid[n] = nutrients[n]?.mean || [];
    grid[`${n}_std`] = nutrients[n]?.std || [];
  }
  return grid;
}

function adaptPoints(measurements) {
  return (measurements?.points || []).map((p) => ({
    id: p.id,
    lat: p.latitude,
    lon: p.longitude,
    N: p.N,
    P: p.P,
    K: p.K,
    sospechoso: Boolean(p.quality?.suspicious),
    valido: p.quality?.valid_for_model !== false,
    motivo: p.quality?.reason,
    metodo: p.quality?.method,
  }));
}

function adaptZones(spatial, proposal) {
  const byZone = new Map((proposal?.recommendations || []).map((r) => [r.zone_id, r]));
  return (spatial?.zones || []).map((zone) => {
    const recommendation = byZone.get(zone.id);
    const assessment = recommendation?.agronomic_assessment;
    const levels = zoneLevels(assessment);
    return {
      id: zone.id,
      celdas: zone.cells,
      area_ha: zone.area?.value,
      npk: zone.centroid_npk,
      incertidumbre: zone.mean_uncertainty?.value,
      metodo: zone.cluster_method,
      nivel: levels,
      peor: worstNivel(levels),
      evaluacion: assessment,
      formulaciones: recommendation?.integer_plan?.formulations || [],
      optimizador: recommendation?.integer_plan?.optimizer,
    };
  });
}

function adaptRisks(climate) {
  return (climate?.risks || []).slice(0, 3).map((risk) => ({
    tipo: risk.type,
    severidad: risk.severity,
    score: risk.score?.value,
    confianza: risk.confidence?.value,
    ventana: risk.window,
    entradas: risk.inputs,
    fuentes: risk.sources || [],
    accion: risk.recommended_action,
    limitaciones: risk.limitations,
  }));
}

export function adapt(pkg) {
  const { plot, measurements, spatial, climate, crop_profile: cropProfile, proposal } = pkg;

  const grid = adaptGrid(spatial.grid);
  const points = adaptPoints(measurements);
  const valid = points.filter((p) => p.valido);
  const rejected = points.filter((p) => !p.valido);
  const zonas = adaptZones(spatial, proposal);

  const insideCells = grid.mask.reduce((acc, m) => acc + m, 0);
  const uncertainCells = grid.mask.reduce(
    (acc, m, i) => acc + (m && grid.sigma[i] > grid.sigma_umbral ? 1 : 0),
    0,
  );

  const areaHa = plot.area?.value;
  const criticalArea = zonas
    .filter((z) => z.peor === 'critico')
    .reduce((acc, z) => acc + (z.area_ha || 0), 0);

  const nextSample = spatial.next_sample && {
    punto: [spatial.next_sample.point.latitude, spatial.next_sample.point.longitude],
    celda: {
      c: spatial.next_sample.grid_cell % grid.cols,
      r: Math.floor(spatial.next_sample.grid_cell / grid.cols),
    },
    incertidumbre: spatial.next_sample.predictive_uncertainty?.value,
    distancia_m: spatial.next_sample.distance_to_nearest_measurement?.value,
    motivo: spatial.next_sample.reason,
    mejora: spatial.next_sample.potential_coverage_improvement,
  };

  const sources = pkg.sources || [];
  const avisos = [...(pkg.warnings || []), ...(climate?.warnings || [])];

  return {
    contrato: pkg.contract_version,
    plot: { ...plot, area_ha: areaHa },
    cultivo: cropProfile,
    grid,
    contorno: plot.boundary,
    puntos: valid,
    descartados: rejected,
    mediciones: points,
    unidadLectura: measurements?.unit,
    zonas,
    nextSample,
    propuesta: proposal && {
      id: proposal.id,
      estado: proposal.status,
      validacion: proposal.validation_status,
      requiere_decision: proposal.human_decision_required,
      aplicada: proposal.applied,
      explicacion: proposal.explanation,
      zonas: zonas.filter((z) => z.formulaciones.length),
    },
    riesgos: adaptRisks(climate),
    estacional: climate?.seasonal_context,
    modelo: pkg.model_run,
    fuentes: sources,
    sampling: {
      total: points.length,
      valid: valid.length,
      rejected: rejected.length,
      suspicious: points.filter((p) => p.sospechoso).length,
      declarado: measurements?.count,
      usado: measurements?.valid_for_model,
    },
    coverage: {
      insideCells,
      uncertainCells,
      uncertainPct: insideCells ? Math.round((uncertainCells / insideCells) * 100) : 0,
    },
    criticalAreaHa: Math.round(criticalArea * 1000) / 1000,
    criticalSharePct: areaHa ? Math.round((criticalArea / areaHa) * 1000) / 10 : 0,
    // The package itself is fresh or not; a stale climate source is reported on
    // its own risk card, not by ageing the whole screen.
    stale: Boolean(pkg.degraded),
    fuentes_vencidas: sources.filter((s) => s.stale || s.failed).length,
    degradado: Boolean(pkg.degraded),
    validacion: pkg.validation_status,
    avisos,
    aviso: avisos[0] || null,
    generado: pkg.generated_at,
    voz: [],
  };
}
