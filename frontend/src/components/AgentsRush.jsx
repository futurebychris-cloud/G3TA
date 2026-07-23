/* Decorative hero graphic: three little AI agents rushing with suitcases —
   pure inline SVG in the brand palette, aria-hidden, no external assets. */
export default function AgentsRush() {
  return (
    <div className="agents-rush" aria-hidden="true">
      <svg viewBox="0 0 380 130" role="presentation">
        <defs>
          <linearGradient id="rushBlue" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#4b8dff" />
            <stop offset="100%" stopColor="#2563eb" />
          </linearGradient>
          <linearGradient id="rushPurple" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#a855f7" />
            <stop offset="100%" stopColor="#7c3aed" />
          </linearGradient>
          <linearGradient id="rushCoral" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#ff8a70" />
            <stop offset="100%" stopColor="#ea4d2b" />
          </linearGradient>
        </defs>

        {/* ground */}
        <line x1="8" y1="118" x2="372" y2="118" stroke="rgba(10,32,52,.18)" strokeWidth="2" strokeDasharray="2 7" strokeLinecap="round" />

        {/* speed lines */}
        <g stroke="rgba(37,99,235,.35)" strokeWidth="3" strokeLinecap="round">
          <line x1="6" y1="52" x2="34" y2="52" />
          <line x1="16" y1="68" x2="52" y2="68" />
          <line x1="128" y1="46" x2="152" y2="46" />
          <line x1="138" y1="64" x2="168" y2="64" />
          <line x1="250" y1="50" x2="276" y2="50" />
          <line x1="258" y1="66" x2="288" y2="66" />
        </g>

        {/* agent 1 — blue, leaning hard, suitcase behind */}
        <g className="rush-agent rush-agent-1"><g transform="rotate(-9 85 80)">
          {/* legs */}
          <path d="M78 96 L66 112" stroke="#132d45" strokeWidth="6" strokeLinecap="round" />
          <path d="M90 96 L100 110" stroke="#132d45" strokeWidth="6" strokeLinecap="round" />
          {/* body */}
          <rect x="66" y="56" width="38" height="44" rx="17" fill="url(#rushBlue)" />
          {/* visor head */}
          <circle cx="85" cy="42" r="17" fill="url(#rushBlue)" />
          <rect x="74" y="36" width="24" height="11" rx="5.5" fill="#0a2034" />
          <circle cx="82" cy="41.5" r="2.6" fill="#cef26f" />
          <circle cx="91" cy="41.5" r="2.6" fill="#cef26f" />
          {/* antenna */}
          <line x1="85" y1="25" x2="85" y2="17" stroke="#0a2034" strokeWidth="3" strokeLinecap="round" />
          <circle cx="85" cy="14" r="4" fill="#cef26f" stroke="#0a2034" strokeWidth="1.5" />
          {/* arm + suitcase */}
          <path d="M68 72 L50 84" stroke="#132d45" strokeWidth="6" strokeLinecap="round" />
          <rect x="30" y="82" width="30" height="24" rx="5" fill="#ffca6b" stroke="#0a2034" strokeWidth="2" />
          <rect x="39" y="76" width="12" height="7" rx="3" fill="none" stroke="#0a2034" strokeWidth="2.4" />
          <line x1="45" y1="82" x2="45" y2="106" stroke="rgba(10,32,52,.28)" strokeWidth="2" />
        </g></g>

        {/* agent 2 — purple, mid stride, suitcase front */}
        <g className="rush-agent rush-agent-2"><g transform="rotate(-7 200 78)">
          <path d="M193 94 L182 111" stroke="#132d45" strokeWidth="6" strokeLinecap="round" />
          <path d="M205 94 L216 108" stroke="#132d45" strokeWidth="6" strokeLinecap="round" />
          <rect x="181" y="54" width="38" height="44" rx="17" fill="url(#rushPurple)" />
          <circle cx="200" cy="40" r="17" fill="url(#rushPurple)" />
          <rect x="189" y="34" width="24" height="11" rx="5.5" fill="#0a2034" />
          <circle cx="197" cy="39.5" r="2.6" fill="#80caff" />
          <circle cx="206" cy="39.5" r="2.6" fill="#80caff" />
          <line x1="200" y1="23" x2="200" y2="15" stroke="#0a2034" strokeWidth="3" strokeLinecap="round" />
          <circle cx="200" cy="12" r="4" fill="#80caff" stroke="#0a2034" strokeWidth="1.5" />
          <path d="M217 70 L234 84" stroke="#132d45" strokeWidth="6" strokeLinecap="round" />
          <rect x="226" y="82" width="32" height="25" rx="5" fill="#80caff" stroke="#0a2034" strokeWidth="2" />
          <rect x="236" y="76" width="12" height="7" rx="3" fill="none" stroke="#0a2034" strokeWidth="2.4" />
          <line x1="242" y1="82" x2="242" y2="107" stroke="rgba(10,32,52,.28)" strokeWidth="2" />
        </g></g>

        {/* agent 3 — coral, sprinting with rolling suitcase */}
        <g className="rush-agent rush-agent-3"><g transform="rotate(-11 315 78)">
          <path d="M308 94 L296 112" stroke="#132d45" strokeWidth="6" strokeLinecap="round" />
          <path d="M320 94 L332 107" stroke="#132d45" strokeWidth="6" strokeLinecap="round" />
          <rect x="296" y="54" width="38" height="44" rx="17" fill="url(#rushCoral)" />
          <circle cx="315" cy="40" r="17" fill="url(#rushCoral)" />
          <rect x="304" y="34" width="24" height="11" rx="5.5" fill="#0a2034" />
          <circle cx="312" cy="39.5" r="2.6" fill="#fffefa" />
          <circle cx="321" cy="39.5" r="2.6" fill="#fffefa" />
          <line x1="315" y1="23" x2="315" y2="15" stroke="#0a2034" strokeWidth="3" strokeLinecap="round" />
          <circle cx="315" cy="12" r="4" fill="#ffca6b" stroke="#0a2034" strokeWidth="1.5" />
          {/* trailing rolling suitcase */}
          <path d="M298 74 L278 92" stroke="#132d45" strokeWidth="6" strokeLinecap="round" />
          <line x1="278" y1="92" x2="262" y2="100" stroke="#0a2034" strokeWidth="3" strokeLinecap="round" />
          <rect x="246" y="92" width="24" height="20" rx="4" fill="#cef26f" stroke="#0a2034" strokeWidth="2" />
          <circle cx="252" cy="115" r="3.5" fill="#0a2034" />
          <circle cx="264" cy="115" r="3.5" fill="#0a2034" />
        </g></g>
      </svg>
    </div>
  )
}
