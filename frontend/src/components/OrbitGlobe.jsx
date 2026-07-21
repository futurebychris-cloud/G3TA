import { Plane } from 'lucide-react'

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
        </defs>

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
      </svg>

      <div className="plane-orbit">
        <span className="plane-capsule"><Plane size={22} strokeWidth={1.8} /></span>
      </div>

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
