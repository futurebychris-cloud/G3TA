export default function OrbitGlobe({ compact = false }) {
  return (
    <div className={`orbit-scene${compact ? ' compact' : ''}`} aria-hidden="true">
      <div className="orbit-halo orbit-halo-one" />
      <div className="orbit-halo orbit-halo-two" />

      <svg className="globe" viewBox="0 0 520 520" role="presentation">
        <defs>
          <radialGradient id="globeFill" cx="35%" cy="28%" r="75%">
            <stop offset="0%" stopColor="#234269" />
            <stop offset="55%" stopColor="#102945" />
            <stop offset="100%" stopColor="#071929" />
          </radialGradient>
          <linearGradient id="landFill" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#d9f66f" />
            <stop offset="100%" stopColor="#86b866" />
          </linearGradient>
          <clipPath id="globeClip">
            <circle cx="260" cy="260" r="191" />
          </clipPath>
          <filter id="softGlow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="7" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <filter id="aircraftShadow" x="-50%" y="-80%" width="200%" height="260%">
            <feGaussianBlur stdDeviation="4" />
          </filter>
          <linearGradient id="aircraftBody" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#fffefa" />
            <stop offset="48%" stopColor="#eaf0f2" />
            <stop offset="100%" stopColor="#aab8c1" />
          </linearGradient>
          <linearGradient id="aircraftWing" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#f8fbfc" />
            <stop offset="100%" stopColor="#b5c1c8" />
          </linearGradient>
          <linearGradient id="cockpitGlass" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#8dd8ff" />
            <stop offset="100%" stopColor="#173a56" />
          </linearGradient>
          <path id="aircraftOrbitPath" d="M47 282C61 141 203 62 362 99C484 127 507 256 449 361C383 480 193 491 89 396C57 367 43 325 47 282Z" />
          <g id="aircraftModel">
            <ellipse className="aircraft-shadow" cx="-3" cy="9" rx="43" ry="12" />
            <g className="aircraft-model">
              <path className="engine-stream engine-stream-upper" d="M-42-11C-53-11-62-9-72-5" />
              <path className="engine-stream engine-stream-lower" d="M-42 11C-53 11-62 9-72 5" />

              <path className="aircraft-tailplane" d="M-27-4L-43-17L-48-17L-40-2V2L-48 17L-43 17L-27 4Z" />
              <path className="aircraft-wing" d="M3-5L-18-30L-27-30L-13-4V4L-27 30L-18 30L3 5L18 4L18-4Z" />
              <path className="aircraft-fuselage" d="M-46 0C-38-5-19-7 8-7H24C33-7 42-4 48 0C42 4 33 7 24 7H8C-19 7-38 5-46 0Z" />
              <path className="aircraft-spine" d="M-34-1H32" />
              <path className="aircraft-cockpit" d="M28-5C35-4 41-2 45 0C41 2 35 4 28 5L24 3V-3Z" />
              <path className="aircraft-tail-fin" d="M-33-3L-41-12L-35-12L-22-3Z" />

              <g className="aircraft-engines">
                <path d="M-9-21C-4-23 2-22 5-18L3-12C-1-10-6-11-10-14Z" />
                <path d="M-9 21C-4 23 2 22 5 18L3 12C-1 10-6 11-10 14Z" />
                <path className="engine-intake" d="M4-18L2-13" />
                <path className="engine-intake" d="M4 18L2 13" />
              </g>

              <path className="aircraft-stripe" d="M-38 0H27" />
              <circle className="navigation-light navigation-light-red" cx="-24" cy="-30" r="2.3" />
              <circle className="navigation-light navigation-light-green" cx="-24" cy="30" r="2.3" />
            </g>
          </g>
        </defs>

        <path className="aircraft-orbit-track" d="M47 282C61 141 203 62 362 99C484 127 507 256 449 361C383 480 193 491 89 396C57 367 43 325 47 282Z" />
        <path className="aircraft-contrail" pathLength="100" d="M47 282C61 141 203 62 362 99C484 127 507 256 449 361C383 480 193 491 89 396C57 367 43 325 47 282Z" />

        <g className="aircraft-pass aircraft-pass-behind">
          <animateMotion dur="14s" repeatCount="indefinite" rotate="auto">
            <mpath href="#aircraftOrbitPath" />
          </animateMotion>
          <g className="aircraft-depth"><use href="#aircraftModel" /></g>
        </g>

        <circle className="globe-shadow" cx="260" cy="278" r="194" />
        <circle cx="260" cy="260" r="191" fill="url(#globeFill)" />

        <g clipPath="url(#globeClip)" className="globe-lines">
          <ellipse cx="260" cy="260" rx="112" ry="191" />
          <ellipse cx="260" cy="260" rx="45" ry="191" />
          <ellipse cx="260" cy="260" rx="174" ry="68" />
          <ellipse cx="260" cy="260" rx="191" ry="130" />
          <path d="M69 260h382" />
        </g>

        <g clipPath="url(#globeClip)" fill="url(#landFill)" className="continents">
          <path d="M124 139l27-22 48-14 30 8 18 22-7 21-30 11-4 20-27 8-8 26-17 7-16-21-25-5-10-23 21-14z" />
          <path d="M205 223l22 8 15 22-8 27 16 17-10 39-18 38-16 31-14-10 1-38-14-29 5-35-13-27 12-29z" />
          <path d="M302 122l36-13 40 16 38 4 14 22-20 17-36-5-20 18-29-4-14-22-28-7z" />
          <path d="M314 187l33-11 26 19 4 24 34 15-10 24-36 1-13 28-9 42-27 25-23-17-5-41-21-31 13-27 21-12z" />
          <path d="M382 334l28-8 25 15 4 23-22 20-31-7-12-24z" />
          <path d="M282 139l10-21 13 8-2 18z" />
        </g>

        <path className="route-line" d="M117 284C194 145 345 136 423 244" />
        <circle className="route-dot start" cx="117" cy="284" r="6" />
        <circle className="route-dot end" cx="423" cy="244" r="6" filter="url(#softGlow)" />

        <g className="aircraft-pass aircraft-pass-front">
          <animateMotion dur="14s" repeatCount="indefinite" rotate="auto">
            <mpath href="#aircraftOrbitPath" />
          </animateMotion>
          <g className="aircraft-depth"><use href="#aircraftModel" /></g>
        </g>
        <g className="aircraft-static" transform="translate(454 345) rotate(112) scale(1.04)">
          <use href="#aircraftModel" />
        </g>
      </svg>

      {!compact && (
        <>
          <div className="globe-label label-origin"><span /> Origin</div>
          <div className="globe-label label-destination"><span /> Somewhere unforgettable</div>
          <div className="globe-chip">
            <span className="live-pulse" />
            Six agents connected
          </div>
        </>
      )}
    </div>
  )
}
