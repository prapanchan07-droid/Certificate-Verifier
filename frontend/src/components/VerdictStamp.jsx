const VERDICT_CONFIG = {
  GENUINE: { color: "#2F6B4F", lines: ["GENUINE"], fontSize: 24 },
  SUSPICIOUS: { color: "#A87C2A", lines: ["SUSPICIOUS"], fontSize: 16 },
  FAKE: { color: "#8C3A2E", lines: ["NOT", "GENUINE"], fontSize: 20 },
  ERROR: { color: "#6B6354", lines: ["UNVERIFIED"], fontSize: 16 },
};

export default function VerdictStamp({ verdict, confidence }) {
  const config = VERDICT_CONFIG[verdict] || VERDICT_CONFIG.ERROR;
  const { color, lines, fontSize } = config;
  const subtext = verdict === "ERROR" ? "FILE UNREADABLE" : `${confidence}% MATCH`;
  // Unique filter id per mount so multiple stamps on a page never collide
  const filterId = `stampGrain-${verdict}-${confidence}`;

  return (
    <div key={`${verdict}-${confidence}`} className="w-36 h-36 shrink-0 animate-stamp">
      <svg
        viewBox="0 0 200 200"
        className="w-full h-full"
        role="img"
        aria-label={`${lines.join(" ")}, ${subtext}`}
      >
        <defs>
          <filter id={filterId} x="-20%" y="-20%" width="140%" height="140%">
            <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="4" result="noise" />
            <feDisplacementMap in="SourceGraphic" in2="noise" scale="2.5" />
          </filter>
        </defs>
        <g filter={`url(#${filterId})`} transform="rotate(-6 100 100)">
          <circle cx="100" cy="100" r="86" fill="none" stroke={color} strokeWidth="3" strokeDasharray="2 5" />
          <circle cx="100" cy="100" r="72" fill="none" stroke={color} strokeWidth="1.5" />

          {lines.length === 1 ? (
            <text
              x="100"
              y="103"
              textAnchor="middle"
              fontFamily="Fraunces, serif"
              fontWeight="600"
              fontSize={fontSize}
              fill={color}
              letterSpacing="1"
            >
              {lines[0]}
            </text>
          ) : (
            <>
              <text x="100" y="92" textAnchor="middle" fontFamily="Fraunces, serif" fontWeight="600" fontSize={fontSize} fill={color} letterSpacing="1">
                {lines[0]}
              </text>
              <text x="100" y="116" textAnchor="middle" fontFamily="Fraunces, serif" fontWeight="600" fontSize={fontSize} fill={color} letterSpacing="1">
                {lines[1]}
              </text>
            </>
          )}

          <text
            x="100"
            y={lines.length === 1 ? 124 : 136}
            textAnchor="middle"
            fontFamily="'IBM Plex Mono', monospace"
            fontSize="9"
            fill={color}
            letterSpacing="1.5"
          >
            {subtext}
          </text>
        </g>
      </svg>
    </div>
  );
}
