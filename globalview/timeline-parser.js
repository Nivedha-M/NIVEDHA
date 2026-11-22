// Turns a Google Maps Timeline export into a simple journey model.
// Supports:
//   - Android on-device export  ({ semanticSegments: [...] })
//   - iOS on-device export      ([ { visit | activity | timelinePath } ])
//   - Older Takeout "Semantic Location History" month files ({ timelineObjects: [...] })
// Everything runs locally in the browser; nothing is uploaded.

(function () {
  const FLIGHT_GUESS_KM = 400; // straight jumps longer than this with no GPS path are drawn as arcs

  const MODE_CATEGORY = {
    FLYING: 'flight',
    IN_TRAIN: 'train', IN_SUBWAY: 'train', IN_TRAM: 'train',
    IN_PASSENGER_VEHICLE: 'car', IN_VEHICLE: 'car', IN_TAXI: 'car', DRIVING: 'car',
    IN_BUS: 'bus',
    MOTORCYCLING: 'motorbike',
    WALKING: 'walk', ON_FOOT: 'walk', RUNNING: 'walk', HIKING: 'walk',
    CYCLING: 'cycle', ON_BICYCLE: 'cycle',
    IN_FERRY: 'boat', SAILING: 'boat', BOATING: 'boat',
  };

  function parseLatLng(v) {
    if (v == null) return null;
    if (typeof v === 'object') {
      if (v.latLng != null) return parseLatLng(v.latLng);
      if (v.latitudeE7 != null) return [v.longitudeE7 / 1e7, v.latitudeE7 / 1e7];
      if (v.latE7 != null) return [v.lngE7 / 1e7, v.latE7 / 1e7];
      return null;
    }
    // "13.0418000°, 80.2341000°"  or  "geo:13.041800,80.234100"
    const m = String(v).replace('geo:', '').match(/(-?\d+(?:\.\d+)?)\D+?(-?\d+(?:\.\d+)?)/);
    if (!m) return null;
    const lat = parseFloat(m[1]), lng = parseFloat(m[2]);
    if (!isFinite(lat) || !isFinite(lng)) return null;
    return [lng, lat]; // GeoJSON order
  }

  function haversineKm(a, b) {
    const R = 6371, r = Math.PI / 180;
    const dLat = (b[1] - a[1]) * r, dLng = (b[0] - a[0]) * r;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * r) * Math.cos(b[1] * r) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
  }

  // Keep longitudes continuous so lines crossing the date line don't wrap around the globe.
  function unwrap(coords) {
    for (let i = 1; i < coords.length; i++) {
      let lng = coords[i][0];
      const prev = coords[i - 1][0];
      while (lng - prev > 180) lng -= 360;
      while (lng - prev < -180) lng += 360;
      coords[i] = [lng, coords[i][1]];
    }
    return coords;
  }

  function greatCircle(a, b, n = 96) {
    const r = Math.PI / 180;
    const lo1 = a[0] * r, la1 = a[1] * r, lo2 = b[0] * r, la2 = b[1] * r;
    const d = 2 * Math.asin(Math.sqrt(Math.sin((la2 - la1) / 2) ** 2 +
      Math.cos(la1) * Math.cos(la2) * Math.sin((lo2 - lo1) / 2) ** 2));
    if (d < 1e-6) return [a, b];
    const out = [];
    for (let i = 0; i <= n; i++) {
      const f = i / n;
      const A = Math.sin((1 - f) * d) / Math.sin(d), B = Math.sin(f * d) / Math.sin(d);
      const x = A * Math.cos(la1) * Math.cos(lo1) + B * Math.cos(la2) * Math.cos(lo2);
      const y = A * Math.cos(la1) * Math.sin(lo1) + B * Math.cos(la2) * Math.sin(lo2);
      const z = A * Math.sin(la1) + B * Math.sin(la2);
      out.push([Math.atan2(y, x) / r, Math.atan2(z, Math.sqrt(x * x + y * y)) / r]);
    }
    return unwrap(out);
  }

  // ---------- format readers: all produce { visits, moves, pathPoints } ----------

  function readSegments(segs) {
    const visits = [], moves = [], pathPoints = [];
    for (const s of segs) {
      const t0 = Date.parse(s.startTime), t1 = Date.parse(s.endTime);
      if (s.visit) {
        const c = s.visit.topCandidate || {};
        const coord = parseLatLng(c.placeLocation);
        if (coord) visits.push({
          t0, t1, coord,
          placeId: c.placeId || c.placeID || null,
          type: c.semanticType || null,
          name: c.sampleName || null,
        });
      } else if (s.activity) {
        const a = s.activity;
        const from = parseLatLng(a.start), to = parseLatLng(a.end);
        if (from && to) moves.push({
          t0, t1, from, to,
          mode: (a.topCandidate && a.topCandidate.type) || 'UNKNOWN',
          distKm: (+a.distanceMeters || 0) / 1000,
          pts: [],
        });
      } else if (Array.isArray(s.timelinePath)) {
        for (const p of s.timelinePath) {
          const coord = parseLatLng(p.point);
          if (!coord) continue;
          const t = p.time ? Date.parse(p.time)
            : t0 + (+p.durationMinutesOffsetFromStartTime || 0) * 60000;
          pathPoints.push({ t, coord });
        }
      }
    }
    return { visits, moves, pathPoints };
  }

  function readLegacy(objs) {
    const visits = [], moves = [];
    const ts = (d, k) => Date.parse(d[k + 'Timestamp'] || '') || +d[k + 'TimestampMs'];
    for (const o of objs) {
      if (o.placeVisit) {
        const pv = o.placeVisit, loc = pv.location || {};
        const coord = parseLatLng(loc);
        if (coord) visits.push({
          t0: ts(pv.duration, 'start'), t1: ts(pv.duration, 'end'), coord,
          placeId: loc.placeId || null, type: loc.semanticType || null,
          name: loc.name || loc.address || null,
        });
      } else if (o.activitySegment) {
        const a = o.activitySegment;
        const from = parseLatLng(a.startLocation), to = parseLatLng(a.endLocation);
        if (!from || !to) continue;
        const raw = (a.waypointPath && a.waypointPath.waypoints) ||
          (a.simplifiedRawPath && a.simplifiedRawPath.points) || [];
        moves.push({
          t0: ts(a.duration, 'start'), t1: ts(a.duration, 'end'), from, to,
          mode: a.activityType || 'UNKNOWN', distKm: (+a.distance || 0) / 1000,
          pts: raw.map(parseLatLng).filter(Boolean),
        });
      }
    }
    return { visits, moves, pathPoints: [] };
  }

  // Assign GPS path points to the activity whose time range contains them.
  function attachPaths(moves, pathPoints) {
    if (!pathPoints.length) return;
    pathPoints.sort((a, b) => a.t - b.t);
    let j = 0;
    for (const m of moves) {
      while (j < pathPoints.length && pathPoints[j].t < m.t0) j++;
      let k = j;
      while (k < pathPoints.length && pathPoints[k].t <= m.t1) { m.pts.push(pathPoints[k].coord); k++; }
    }
  }

  function prettyType(type) {
    switch (type) {
      case 'HOME': case 'INFERRED_HOME': return 'Home';
      case 'WORK': case 'INFERRED_WORK': return 'Work';
      case 'SEARCHED_ADDRESS': return 'Searched place';
      default: return null;
    }
  }

  // ---------- build the journey model ----------

  function build({ visits, moves, pathPoints }) {
    attachPaths(moves, pathPoints);

    // Unique places
    const places = [];
    const byKey = new Map();
    const placeKey = (v) => v.placeId || `${v.coord[1].toFixed(3)},${v.coord[0].toFixed(3)}`;

    const events = [
      ...visits.filter(v => isFinite(v.t0)).map(v => ({ kind: 'visit', ...v })),
      ...moves.filter(m => isFinite(m.t0)).map(m => ({ kind: 'move', ...m })),
    ].sort((a, b) => a.t0 - b.t0 || (a.kind === 'visit' ? -1 : 1));

    events.forEach((ev, idx) => {
      ev.idx = idx;
      if (ev.kind === 'visit') {
        const key = placeKey(ev);
        let p = byKey.get(key);
        if (!p) {
          p = {
            id: places.length, key, coord: ev.coord, name: ev.name, type: ev.type,
            count: 0, totalMs: 0, first: ev.t0, last: ev.t1, firstEvent: idx,
          };
          byKey.set(key, p);
          places.push(p);
        }
        p.count++;
        p.totalMs += Math.max(0, (ev.t1 || ev.t0) - ev.t0);
        p.last = Math.max(p.last, ev.t1 || ev.t0);
        if (!p.name && ev.name) p.name = ev.name;
        if (!p.type || p.type === 'UNKNOWN') p.type = ev.type;
        ev.place = p.id;
      } else {
        ev.cat = MODE_CATEGORY[ev.mode] || 'other';
        const straightKm = haversineKm(ev.from, ev.to);
        if (!ev.distKm) ev.distKm = straightKm;
        const isFlight = ev.cat === 'flight' || (ev.pts.length < 2 && straightKm > FLIGHT_GUESS_KM);
        if (isFlight) ev.cat = 'flight';
        ev.path = isFlight ? greatCircle(ev.from, ev.to) : unwrap([ev.from, ...ev.pts, ev.to]);
      }
    });

    places.forEach(p => { p.label = p.name || prettyType(p.type) || `${p.coord[1].toFixed(3)}, ${p.coord[0].toFixed(3)}`; });

    // Name each move by its neighbouring visits
    let lastVisit = null;
    for (const ev of events) {
      if (ev.kind === 'visit') lastVisit = ev;
      else ev.fromLabel = lastVisit ? places[lastVisit.place].label : null;
    }
    let nextVisit = null;
    for (let i = events.length - 1; i >= 0; i--) {
      const ev = events[i];
      if (ev.kind === 'visit') nextVisit = ev;
      else ev.toLabel = nextVisit ? places[nextVisit.place].label : null;
    }

    const moveEvents = events.filter(e => e.kind === 'move');
    const t0 = events.length ? events[0].t0 : 0;
    const t1 = events.length ? Math.max(...events.map(e => e.t1 || e.t0)) : 0;
    const stats = {
      places: places.length,
      trips: moveEvents.length,
      flights: moveEvents.filter(m => m.cat === 'flight').length,
      km: moveEvents.reduce((s, m) => s + m.distKm, 0),
      days: events.length ? Math.max(1, Math.round((t1 - t0) / 86400000)) : 0,
      t0, t1,
    };
    return { events, places, stats };
  }

  function parseTimeline(raw) {
    let parts;
    if (Array.isArray(raw)) parts = readSegments(raw);
    else if (raw && Array.isArray(raw.semanticSegments)) parts = readSegments(raw.semanticSegments);
    else if (raw && Array.isArray(raw.timelineObjects)) parts = readLegacy(raw.timelineObjects);
    else if (raw && Array.isArray(raw.locations)) {
      throw new Error('This is a raw "Records.json" file. Please use the Timeline export from your phone instead.');
    } else {
      throw new Error('Unrecognised file. Expected a Google Maps Timeline export (Timeline.json).');
    }
    const model = build(parts);
    if (!model.events.length) throw new Error('No visits or trips found in this file.');
    return model;
  }

  window.TimelineParser = { parseTimeline, haversineKm };
})();
