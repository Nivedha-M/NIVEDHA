# Global View

A 3D globe of your Google Maps Timeline. It's free and open source, needs no API keys, and all processing happens in your browser.

## Run it

```bash
cd ~/Downloads/globalview && python3 -m http.server 8765 --bind 127.0.0.1
```

Then open http://localhost:8765. It starts with fictional sample data. Click **Load Timeline.json** (or drag the file onto the page) to see your own journey.

## Get your data

- **Android:** Settings → Location → Location services → Timeline → Export Timeline data
- **iPhone:** Google Maps → profile → Your Timeline → ⋯ → Location & privacy settings → Export Timeline data

Older Takeout "Semantic Location History" files work too.

## Built with

- [MapLibre GL JS](https://maplibre.org/) (BSD-3): the globe and map rendering
- [OpenFreeMap](https://openfreemap.org/): free vector map tiles (Dark, Streets, Light)
- [NASA GIBS](https://earthdata.nasa.gov/gibs): Night lights and Blue Marble imagery

## Files

- `index.html`: the page layout and styles
- `app.js`: the globe, layers, replay and file loading
- `timeline-parser.js`: turns a Timeline export into places and trips
- `sample-data.js`: fictional demo journey (same format as a real export)

`Timeline.json` is your private location history. Don't commit it or share it.
