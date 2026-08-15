// Minimal Web Mercator tile layer against OpenStreetMap, no map library.

const TILE_SIZE = 256;
const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
export const ATTRIBUTION = '© OpenStreetMap';

export function project(lat, lon, zoom) {
  const scale = TILE_SIZE * 2 ** zoom;
  const rad = (lat * Math.PI) / 180;
  return {
    x: ((lon + 180) / 360) * scale,
    y: ((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * scale,
  };
}

export function fitZoom(boundsGeo, widthPx, heightPx, maxZoom = 19) {
  for (let zoom = maxZoom; zoom > 1; zoom -= 1) {
    const a = project(boundsGeo.north, boundsGeo.west, zoom);
    const b = project(boundsGeo.south, boundsGeo.east, zoom);
    if (Math.abs(b.x - a.x) <= widthPx && Math.abs(b.y - a.y) <= heightPx) return zoom;
  }
  return 2;
}

export function renderTiles(container, boundsGeo, widthPx, heightPx) {
  const zoom = fitZoom(boundsGeo, widthPx, heightPx);
  const topLeft = project(boundsGeo.north, boundsGeo.west, zoom);
  const bottomRight = project(boundsGeo.south, boundsGeo.east, zoom);
  const spanX = bottomRight.x - topLeft.x;
  const spanY = bottomRight.y - topLeft.y;
  const originX = topLeft.x - (widthPx - spanX) / 2;
  const originY = topLeft.y - (heightPx - spanY) / 2;

  const fromTile = { x: Math.floor(originX / TILE_SIZE), y: Math.floor(originY / TILE_SIZE) };
  const toTile = {
    x: Math.floor((originX + widthPx) / TILE_SIZE),
    y: Math.floor((originY + heightPx) / TILE_SIZE),
  };

  container.innerHTML = '';
  const max = 2 ** zoom;
  for (let ty = fromTile.y; ty <= toTile.y; ty += 1) {
    for (let tx = fromTile.x; tx <= toTile.x; tx += 1) {
      if (ty < 0 || ty >= max) continue;
      const img = document.createElement('img');
      img.src = TILE_URL.replace('{z}', zoom).replace('{x}', ((tx % max) + max) % max).replace('{y}', ty);
      img.alt = '';
      img.loading = 'eager';
      img.decoding = 'async';
      img.style.cssText = `position:absolute;width:${TILE_SIZE}px;height:${TILE_SIZE}px;`
        + `left:${tx * TILE_SIZE - originX}px;top:${ty * TILE_SIZE - originY}px;`;
      img.addEventListener('error', () => img.remove());
      container.appendChild(img);
    }
  }

  return {
    zoom,
    toPixel(lat, lon) {
      const point = project(lat, lon, zoom);
      return { x: point.x - originX, y: point.y - originY };
    },
  };
}
