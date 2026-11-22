// Global View — 3D globe of your Google Maps Timeline, built on MapLibre GL JS (open source)
// with free OpenFreeMap / NASA GIBS tiles. No API keys, no uploads.

(function () {
  const { parseTimeline } = window.TimelineParser;

  // ---------- config ----------
  const CATS = {
    flight:    { label: 'Flight',    icon: '✈️', color: '#f6b73c' },
    train:     { label: 'Train',     icon: '🚆', color: '#8ea2ff' },
    car:       { label: 'Car',       icon: '🚗', color: '#34d3c6' },
    bus:       { label: 'Bus',       icon: '🚌', color: '#4fb6f7' },
    motorbike: { label: 'Motorbike', icon: '🏍️', color: '#ff6b8b' },
    walk:      { label: 'Walk',      icon: '🚶', color: '#a3e635' },
    cycle:     { label: 'Cycle',     icon: '🚲', color: '#c084fc' },
    boat:      { label: 'Boat',      icon: '⛴️', color: '#38bdf8' },
    other:     { label: 'Other',     icon: '•',  color: '#9ca3af' },
  };
  const PLACE_COLOR = '#f6b73c';

  const nasa = (layer, ext, date) => ({
    version: 8,
    sources: {
      nasa: {
        type: 'raster', tileSize: 256, maxzoom: 8,
        tiles: [`https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${layer}/default/${date ? date + '/' : ''}GoogleMapsCompatible_Level8/{z}/{y}/{x}.${ext}`],
        attribution: 'Imagery © NASA EOSDIS GIBS',
      },
    },
    layers: [{ id: 'nasa', type: 'raster', source: 'nasa' }],
  });
  const STYLES = {
    dark: 'https://tiles.openfreemap.org/styles/dark',
    liberty: 'https://tiles.openfreemap.org/styles/liberty',
    positron: 'https://tiles.openfreemap.org/styles/positron',
    night: nasa('VIIRS_Black_Marble', 'png', '2016-01-01'),
    bluemarble: nasa('BlueMarble_ShadedRelief_Bathymetry', 'jpeg'),
  };

  // ---------- state ----------
  let model = null;              // { events, places, stats }
  let cursor = 0;                // index of last event shown
  let enabledCats = new Set(Object.keys(CATS));
  let playToken = 0;             // bumps to cancel a running replay
  let playing = false;
  let spinning = true;           // idle globe rotation
  let activePopup = null;

  const $ = (id) => document.getElementById(id);
  const fmtDate = (t) => new Date(t).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
  const fmtKm = (km) => km >= 100 ? Math.round(km).toLocaleString() : km.toFixed(1);
  const esc = (s) => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmtDuration = (ms) => {
    const h = ms / 3600000;
    if (h < 1) return `${Math.round(h * 60)} min`;
    if (h < 48) return `${h.toFixed(h < 10 ? 1 : 0)} h`;
    return `${Math.round(h / 24)} days`;
  };

  // ---------- map ----------
  const map = new maplibregl.Map({
    container: 'map',
    style: STYLES.dark,
    center: [60, 20],
    zoom: 1.6,
    maxPitch: 75,
    attributionControl: { compact: true },
  });
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');
  const mapReady = new Promise((resolve) => map.once('load', resolve));

  map.on('style.load', () => {
    map.setProjection({ type: 'globe' });
    try {
      map.setSky({
        'sky-color': '#0b1a3a',
        'horizon-color': '#4a78c2',
        'fog-color': '#0b1a3a',
        'sky-horizon-blend': 0.6,
        'horizon-fog-blend': 0.6,
        'fog-ground-blend': 0.9,
        'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 5, 1, 7, 0],
      });
    } catch (e) { /* older engines: no atmosphere */ }
    addJourneyLayers();
  });

  function emptyFC() { return { type: 'FeatureCollection', features: [] }; }

  function movesFC() {
    if (!model) return emptyFC();
    return {
      type: 'FeatureCollection',
      features: model.events.filter(e => e.kind === 'move').map(e => ({
        type: 'Feature',
        properties: { idx: e.idx, cat: e.cat, color: CATS[e.cat].color },
        geometry: { type: 'LineString', coordinates: e.path },
      })),
    };
  }

  function placesFC() {
    if (!model) return emptyFC();
    return {
      type: 'FeatureCollection',
      features: model.places.map(p => ({
        type: 'Feature',
        properties: { id: p.id, count: p.count, firstEvent: p.firstEvent },
        geometry: { type: 'Point', coordinates: p.coord },
      })),
    };
  }

  function addJourneyLayers() {
    map.addSource('moves', { type: 'geojson', data: movesFC() });
    map.addSource('active', { type: 'geojson', data: emptyFC() });
    map.addSource('places', { type: 'geojson', data: placesFC() });
    map.addSource('current', { type: 'geojson', data: emptyFC() });

    const ground = ['!=', ['get', 'cat'], 'flight'];
    const flight = ['==', ['get', 'cat'], 'flight'];

    map.addLayer({ id: 'moves-glow', type: 'line', source: 'moves',
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': ['get', 'color'], 'line-width': ['interpolate', ['linear'], ['zoom'], 1, 4, 10, 9], 'line-blur': 4, 'line-opacity': 0.35 } });
    map.addLayer({ id: 'moves-ground', type: 'line', source: 'moves', filter: ground,
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': ['get', 'color'], 'line-width': ['interpolate', ['linear'], ['zoom'], 1, 1.2, 10, 3.5] } });
    map.addLayer({ id: 'moves-flight', type: 'line', source: 'moves', filter: flight,
      layout: { 'line-join': 'round' },
      paint: { 'line-color': ['get', 'color'], 'line-width': 1.6, 'line-dasharray': [3, 2] } });

    map.addLayer({ id: 'active-glow', type: 'line', source: 'active',
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': ['get', 'color'], 'line-width': 12, 'line-blur': 6, 'line-opacity': 0.6 } });
    map.addLayer({ id: 'active-line', type: 'line', source: 'active',
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': '#ffffff', 'line-width': 3 } });

    map.addLayer({ id: 'places-halo', type: 'circle', source: 'places',
      paint: {
        'circle-color': PLACE_COLOR, 'circle-opacity': 0.18, 'circle-blur': 0.6,
        'circle-radius': ['interpolate', ['linear'], ['get', 'count'], 1, 10, 20, 22],
        'circle-pitch-alignment': 'map',
      } });
    map.addLayer({ id: 'places-dot', type: 'circle', source: 'places',
      paint: {
        'circle-color': '#fff7e6', 'circle-stroke-color': PLACE_COLOR, 'circle-stroke-width': 2,
        'circle-radius': ['interpolate', ['linear'], ['get', 'count'], 1, 3.5, 20, 7],
      } });

    map.addLayer({ id: 'current-pulse', type: 'circle', source: 'current',
      paint: { 'circle-color': '#ffffff', 'circle-opacity': 0.25, 'circle-radius': 14, 'circle-blur': 0.4 } });
    map.addLayer({ id: 'current-dot', type: 'circle', source: 'current',
      paint: { 'circle-color': '#ffffff', 'circle-radius': 5, 'circle-stroke-color': '#000', 'circle-stroke-width': 1 } });

    applyFilters();
    if (model && model.events[cursor]) {
      const ev = model.events[cursor];
      setCurrent(ev.kind === 'visit' ? ev.coord : ev.to);
    }
  }

  function setData(id, data) { const s = map.getSource(id); if (s) s.setData(data); }

  function applyFilters(moveLimit = cursor) {
    if (!map.getLayer('moves-ground')) return;
    const cats = ['in', ['get', 'cat'], ['literal', [...enabledCats]]];
    const upto = ['<=', ['get', 'idx'], moveLimit];
    map.setFilter('moves-glow', ['all', upto, cats]);
    map.setFilter('moves-ground', ['all', upto, cats, ['!=', ['get', 'cat'], 'flight']]);
    map.setFilter('moves-flight', ['all', upto, cats, ['==', ['get', 'cat'], 'flight']]);
    const placeFilter = ['<=', ['get', 'firstEvent'], cursor];
    map.setFilter('places-halo', placeFilter);
    map.setFilter('places-dot', placeFilter);
  }

  // Pulse the current-position marker
  (function pulse() {
    if (map.getLayer('current-pulse')) {
      const t = (performance.now() % 1600) / 1600;
      map.setPaintProperty('current-pulse', 'circle-radius', 6 + t * 22);
      map.setPaintProperty('current-pulse', 'circle-opacity', 0.45 * (1 - t));
    }
    requestAnimationFrame(pulse);
  })();

  function setCurrent(coord) {
    setData('current', coord ? { type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: coord } } : emptyFC());
  }

  // ---------- idle spin ----------
  function spin() {
    if (!spinning || playing || map.getZoom() > 4) return;
    const c = map.getCenter();
    c.lng -= 6;
    map.easeTo({ center: c, duration: 2000, easing: (n) => n });
  }
  map.on('moveend', spin);
  map.on('load', () => setTimeout(spin, 600));
  ['mousedown', 'touchstart', 'wheel'].forEach(ev =>
    map.getCanvasContainer().addEventListener(ev, () => { spinning = false; }, { passive: true }));

  // ---------- popups ----------
  map.on('click', 'places-dot', (e) => openPlacePopup(model.places[e.features[0].properties.id]));
  map.on('mouseenter', 'places-dot', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'places-dot', () => { map.getCanvas().style.cursor = ''; });

  function openPlacePopup(p) {
    if (activePopup) activePopup.remove();
    const when = p.count > 1 ? `${fmtDate(p.first)} → ${fmtDate(p.last)}` : fmtDate(p.first);
    activePopup = new maplibregl.Popup({ offset: 12, maxWidth: '260px' })
      .setLngLat(p.coord)
      .setHTML(`<div class="pop"><h3>${esc(p.label)}</h3>
        <div>${p.count} visit${p.count > 1 ? 's' : ''} · ${fmtDuration(p.totalMs)} total</div>
        <div>${when}</div></div>`)
      .addTo(map);
  }

  // ---------- UI: panel ----------
  function renderPanel(sourceLabel) {
    const { stats, places, events } = model;
    $('source').innerHTML = `<span class="pill">${esc(sourceLabel)}</span><span>${fmtDate(stats.t0)} – ${fmtDate(stats.t1)}</span>`;
    $('sPlaces').textContent = stats.places.toLocaleString();
    $('sDist').textContent = Math.round(stats.km).toLocaleString();
    $('sTrips').textContent = stats.trips.toLocaleString();
    $('sDays').textContent = stats.days.toLocaleString();

    // Legend with per-mode totals
    const totals = {};
    for (const e of events) if (e.kind === 'move') {
      totals[e.cat] = totals[e.cat] || { n: 0, km: 0 };
      totals[e.cat].n++; totals[e.cat].km += e.distKm;
    }
    $('legend').innerHTML = Object.entries(CATS).filter(([k]) => totals[k]).map(([k, c]) =>
      `<span class="chip ${enabledCats.has(k) ? '' : 'off'}" data-cat="${k}" title="${totals[k].n} trips">
        <i style="background:${c.color}"></i>${c.label} · ${fmtKm(totals[k].km)} km</span>`).join('');

    const MAX = 500;
    const sorted = [...places].sort((a, b) => a.first - b.first);
    $('places').innerHTML = sorted.slice(0, MAX).map(p =>
      `<div class="place" data-id="${p.id}"><span class="dot"></span>
        <span class="name">${esc(p.label)}</span>
        <span class="meta">${p.count > 1 ? p.count + '× · ' : ''}${fmtDate(p.first)}</span></div>`).join('') +
      (sorted.length > MAX ? `<div class="place"><span class="meta">+ ${sorted.length - MAX} more</span></div>` : '');
  }

  $('legend').addEventListener('click', (e) => {
    const chip = e.target.closest('.chip');
    if (!chip) return;
    const k = chip.dataset.cat;
    enabledCats.has(k) ? enabledCats.delete(k) : enabledCats.add(k);
    chip.classList.toggle('off');
    applyFilters();
  });

  $('places').addEventListener('click', (e) => {
    const row = e.target.closest('.place[data-id]');
    if (!row) return;
    stop();
    spinning = false;
    const p = model.places[+row.dataset.id];
    if (cursor < p.firstEvent) showAt(model.events.length - 1);
    map.flyTo({ center: p.coord, zoom: Math.max(map.getZoom(), 11), duration: 2200, essential: true });
    openPlacePopup(p);
    if (window.innerWidth <= 760) $('panel').classList.remove('open');
  });

  // ---------- UI: timeline ----------
  function describe(ev) {
    if (ev.kind === 'visit') return `📍 ${model.places[ev.place].label}`;
    const c = CATS[ev.cat];
    const route = ev.fromLabel && ev.toLabel ? ` · ${ev.fromLabel} → ${ev.toLabel}` : '';
    return `${c.icon} ${c.label}${route} · ${fmtKm(ev.distKm)} km`;
  }

  function updateNow(i) {
    const ev = model.events[i];
    $('scrub').value = i;
    $('nowText').textContent = describe(ev);
    $('nowDate').textContent = fmtDate(ev.t0);
  }

  function showAt(i) {
    cursor = i;
    applyFilters();
    setData('active', emptyFC());
    const ev = model.events[i];
    setCurrent(ev.kind === 'visit' ? ev.coord : ev.to);
    updateNow(i);
  }

  $('scrub').addEventListener('input', (e) => { stop(); showAt(+e.target.value); });

  // ---------- replay ----------
  const speed = () => +$('speed').value;

  function wait(ms, tok) {
    return new Promise((res) => {
      const start = performance.now();
      (function tick() {
        if (tok !== playToken || performance.now() - start >= ms) res();
        else requestAnimationFrame(tick);
      })();
    });
  }

  function lineLengths(coords) {
    const acc = [0];
    for (let i = 1; i < coords.length; i++) {
      const dx = coords[i][0] - coords[i - 1][0], dy = coords[i][1] - coords[i - 1][1];
      acc.push(acc[i - 1] + Math.hypot(dx, dy));
    }
    return acc;
  }

  function partialLine(coords, acc, f) {
    const target = acc[acc.length - 1] * f;
    const out = [coords[0]];
    for (let i = 1; i < coords.length; i++) {
      if (acc[i] <= target) { out.push(coords[i]); continue; }
      const seg = acc[i] - acc[i - 1] || 1;
      const t = (target - acc[i - 1]) / seg;
      out.push([coords[i - 1][0] + (coords[i][0] - coords[i - 1][0]) * t,
                coords[i - 1][1] + (coords[i][1] - coords[i - 1][1]) * t]);
      break;
    }
    if (out.length < 2) out.push(coords[0]);
    return out;
  }

  function animateMove(ev, ms, tok) {
    const acc = lineLengths(ev.path);
    const color = CATS[ev.cat].color;
    const ease = (t) => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    return new Promise((res) => {
      const start = performance.now();
      (function frame() {
        if (tok !== playToken) return res();
        const f = Math.min(1, (performance.now() - start) / ms);
        const line = partialLine(ev.path, acc, ease(f));
        setData('active', { type: 'Feature', properties: { color }, geometry: { type: 'LineString', coordinates: line } });
        setCurrent(line[line.length - 1]);
        if (f < 1) requestAnimationFrame(frame); else res();
      })();
    });
  }

  function boundsOf(coords) {
    const b = new maplibregl.LngLatBounds(coords[0], coords[0]);
    for (const c of coords) b.extend(c);
    return b;
  }

  function cameraPadding() {
    const small = window.innerWidth <= 760;
    return small ? { top: 80, bottom: 120, left: 30, right: 30 } : { top: 80, bottom: 140, left: 380, right: 80 };
  }

  async function step(i, tok) {
    const ev = model.events[i];
    updateNow(i);
    if (ev.kind === 'move') {
      if (!enabledCats.has(ev.cat)) { cursor = i; applyFilters(); return; }
      const isFlight = ev.cat === 'flight';
      const ms = (isFlight ? 4200 : Math.min(3200, 1400 + ev.distKm * 8)) / speed();
      applyFilters(i - 1);
      map.fitBounds(boundsOf(ev.path), {
        padding: cameraPadding(), maxZoom: 13, duration: ms * 0.8, essential: true,
        ...(isFlight ? { pitch: 0, bearing: 0 } : {}),
      });
      await animateMove(ev, ms, tok);
      if (tok !== playToken) return;
      cursor = i;
      applyFilters();
      setData('active', emptyFC());
    } else {
      cursor = i;
      applyFilters();
      setCurrent(ev.coord);
      const isNew = model.places[ev.place].firstEvent === i;
      await wait((isNew ? 1100 : 450) / speed(), tok);
    }
  }

  async function play() {
    if (!model) return;
    stop();
    const tok = ++playToken;
    playing = true; spinning = false;
    $('play').textContent = '❚❚';
    if (activePopup) activePopup.remove();
    let i = cursor >= model.events.length - 1 ? 0 : cursor + 1;
    if (i === 0) { cursor = -1; applyFilters(); }
    for (; i < model.events.length && tok === playToken; i++) await step(i, tok);
    if (tok === playToken) { playing = false; $('play').textContent = '▶'; }
  }

  function stop() {
    playToken++;
    playing = false;
    $('play').textContent = '▶';
    if (map.getSource('active')) setData('active', emptyFC());
  }

  $('play').addEventListener('click', () => (playing ? stop() : play()));

  // ---------- loading data ----------
  function fitAll(duration = 2500) {
    if (!model) return;
    const coords = model.places.map(p => p.coord);
    if (!coords.length) return;
    const b = boundsOf(coords);
    const spanDeg = Math.max(b.getEast() - b.getWest(), b.getNorth() - b.getSouth());
    if (spanDeg > 60) map.flyTo({ center: b.getCenter(), zoom: 1.6, pitch: 0, bearing: 0, duration });
    else map.fitBounds(b, { padding: cameraPadding(), duration, maxZoom: 12, pitch: 0, bearing: 0 });
  }

  function loadModel(raw, label) {
    stop();
    model = parseTimeline(raw);
    enabledCats = new Set(Object.keys(CATS));
    $('scrub').max = model.events.length - 1;
    renderPanel(label);
    setData('moves', movesFC());
    setData('places', placesFC());
    showAt(model.events.length - 1);
  }

  function toast(msg, ms = 5000) {
    const el = $('toast');
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.remove('show'), ms);
  }

  function readFile(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        loadModel(JSON.parse(reader.result), file.name);
        spinning = false;
        fitAll();
        toast(`Loaded ${model.stats.places} places and ${model.stats.trips} trips from ${file.name}. Nothing left your computer.`);
      } catch (err) {
        console.error(err);
        toast('Could not read that file: ' + err.message, 8000);
      }
    };
    reader.readAsText(file);
  }

  $('load').addEventListener('click', () => $('file').click());
  $('file').addEventListener('change', (e) => readFile(e.target.files[0]));
  $('fit').addEventListener('click', () => { stop(); fitAll(); });
  $('panelToggle').addEventListener('click', () => $('panel').classList.toggle('open'));

  let dragDepth = 0;
  window.addEventListener('dragenter', (e) => { e.preventDefault(); dragDepth++; $('drop').classList.add('show'); });
  window.addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; $('drop').classList.remove('show'); } });
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('drop', (e) => {
    e.preventDefault(); dragDepth = 0; $('drop').classList.remove('show');
    readFile(e.dataTransfer.files[0]);
  });

  $('style').addEventListener('change', (e) => {
    stop();
    map.setStyle(STYLES[e.target.value], { diff: false });
  });

  // Start with Timeline.json from this folder if it's there (served locally), else the sample.
  // Add ?sample to the URL to force the sample data.
  async function boot() {
    if (!new URLSearchParams(location.search).has('sample') && location.protocol.startsWith('http')) {
      try {
        const res = await fetch('Timeline.json', { cache: 'no-store' });
        if (res.ok) {
          loadModel(await res.json(), 'Timeline.json');
          spinning = false;
          await mapReady;
          setTimeout(() => fitAll(2500), 400);
          return;
        }
      } catch (err) {
        console.warn('Timeline.json not loaded, using sample data:', err);
      }
    }
    loadModel(window.SAMPLE_TIMELINE, 'Sample data');
  }
  boot();

  // Expose for debugging in the console
  window.globalView = { map, get model() { return model; }, loadModel };
})();
