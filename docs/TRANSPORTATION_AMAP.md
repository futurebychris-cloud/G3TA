# Transportation Agent + AMap route UI

This feature keeps the original Transportation Agent contract and adds optional
map metadata:

- `route_points`: departure and arrival airport coordinates when the provider
  supplies them. Coordinates passed to the frontend must be GCJ-02 / AMap-compatible;
  convert GPS/WGS84 provider coordinates with AMap's coordinate-conversion API first.
- `route_summary`: the selected carrier, airports, duration, departure time and
  stop count.
- `coverage`: requested and currently available transportation modes.

The React map combines those transportation points with the existing hotel and activity
coordinates already present in the final itinerary. It does not make the
Transportation Agent read Housing or Activity data.

## Local AMap configuration

Create a Web JS API 2.0 key and security code in the AMap developer console, then
fill in the ignored repository-root `.env.local` file:

```dotenv
VITE_AMAP_KEY=your_web_js_key
VITE_AMAP_SECURITY_CODE=your_security_code
```

Restart Vite after changing either value. `frontend/vite.config.js` uses the
repository root as its environment directory.

An itinerary outside mainland China is an overseas-map scenario. The AMap key must
have the corresponding advanced map and overseas route-planning permissions. This
permission is not a checkbox in the Key settings dialog: request it through the AMap
console ticket center under `商务咨询 -> 海外解决方案`. Include the target country,
JS API 2.0, required Walking/Driving services, expected daily calls and QPS. Without
approval, the base map or route results may be unavailable even when the key is valid.

Official references:

- JS API loader: https://developer.amap.com/api/javascript-api-v2/getting-started
- Route planning: https://developer.amap.com/api/javascript-api-v2/guide/services/navigation
- Security code: https://developer.amap.com/api/javascript-api-v2/guide/abc/jscode
- Coordinate conversion: https://developer.amap.com/api/javascript-api-v2/guide/transform/convertfrom
- Multi-language / overseas map capability: https://developer.amap.com/api/javascript-api-v2/guide/map/englishmap
- Overseas privilege error codes: https://developer.amap.com/api/webservice/guide/tools/info
- Overseas test quota FAQ: https://lbs.amap.com/faq/quota-key/quota/42908
- Ticket center: https://console.amap.com/dev/ticket/list

## Display behavior

- `Full trip`: gradually reveals the mapped local itinerary.
- `Day N`: requests `hotel -> mapped activities/meals -> hotel` segments.
- `Walking` / `Driving`: requests a real AMap route for each local segment, so
  the two modes use different provider paths.
- A car transportation recommendation requests an AMap driving route.
- Flight and train endpoints use a clearly labeled geographic overview; it is
  not presented as a provider-confirmed carrier track.
- Reduced Motion shows the route immediately without the reveal animation.
- Missing credentials or loader failures show an explicit configuration/error
  panel rather than a fake route.

Only records with valid latitude/longitude pairs are displayed. Generated terminal,
hotel and activity coordinates are planning estimates and must be checked before use.
Unresolved named POIs are skipped instead of being stacked at the city center.

## Local checks

```bash
cd backend
python -m unittest discover -s tests -v
python _smoke_test.py

cd ../frontend
npm test
npm run build
npm run dev
```

Real keys must never be committed. For production, replace the local plaintext
security-code setup with AMap's server-proxy security mode.
Any key that has appeared in Git history must be treated as exposed and rotated before reuse.
