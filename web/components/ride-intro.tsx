"use client";

import { useEffect, useRef, useState } from "react";

/**
 * The ride — a scroll-driven London→Paris opening. Scrolling pedals a
 * cyclist through a side-scrolling world; product powers appear as story
 * beats at waypoints (weather, elevation, ferry, lodging). Ends at the
 * Eiffel Tower with a CTA that focuses the chat.
 *
 * NOTE: the app's scroll container is <main>, not the window — progress is
 * derived from getBoundingClientRect, which is scroller-agnostic.
 */

const WORLD_W = 8800;
/* Tall ground: the app's chat bar overlays the bottom ~130px of the
   viewport, so the riding surface sits well above it. */
const GROUND_H = 230;
const TRIP_KM = 364;
/* World x the ride ends at — the cyclist always finishes at the foot of
   the Eiffel Tower, whatever the viewport width. */
const TOWER_ANCHOR = 5470;

/* ---------- the cyclist ---------- */

function Cyclist({ frame }: { frame: "a" | "b" }) {
  const a = frame === "a";
  return (
    <svg width={150} height={112} viewBox="0 0 150 112" aria-hidden="true">
      {/* wheels */}
      {[38, 112].map((cx) => (
        <g key={cx}>
          <circle cx={cx} cy={86} r={22} fill="none" stroke="#0A0A09" strokeWidth="5" />
          <g className="wheel-spin" style={{ transformOrigin: `${cx}px 86px` }}>
            <line x1={cx} y1={66} x2={cx} y2={106} stroke="#0A0A09" strokeWidth="2" />
            <line x1={cx - 20} y1={86} x2={cx + 20} y2={86} stroke="#0A0A09" strokeWidth="2" />
            <line x1={cx - 14} y1={72} x2={cx + 14} y2={100} stroke="#0A0A09" strokeWidth="1.6" />
          </g>
          <circle cx={cx} cy={86} r={3.5} fill="#0A0A09" />
        </g>
      ))}
      {/* frame */}
      <path
        d="M38 86 L66 52 L104 52 L112 86 M66 52 L75 84 L38 86 M75 84 L104 52"
        fill="none"
        stroke="#FF3D14"
        strokeWidth="5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* seat + handlebar */}
      <line x1={60} y1={46} x2={74} y2={46} stroke="#0A0A09" strokeWidth="5" strokeLinecap="round" />
      <path d="M104 52 L104 40 L116 38" fill="none" stroke="#0A0A09" strokeWidth="4.5" strokeLinecap="round" />
      {/* pedals + legs */}
      <circle cx={75} cy={84} r={5} fill="#0A0A09" />
      {a ? (
        <>
          <path d="M67 46 L58 66 L80 74" fill="none" stroke="#123B8A" strokeWidth="7.5" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M67 46 L80 60 L69 92" fill="none" stroke="#1D4FB0" strokeWidth="7.5" strokeLinecap="round" strokeLinejoin="round" />
        </>
      ) : (
        <>
          <path d="M67 46 L82 62 L84 78" fill="none" stroke="#123B8A" strokeWidth="7.5" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M67 46 L60 68 L64 90" fill="none" stroke="#1D4FB0" strokeWidth="7.5" strokeLinecap="round" strokeLinejoin="round" />
        </>
      )}
      {/* torso — leaning forward, brand jersey */}
      <path d="M67 48 L98 34" stroke="#FF3D14" strokeWidth="11" strokeLinecap="round" />
      {/* arm */}
      <path d="M92 38 L112 40" stroke="#f2b98c" strokeWidth="6" strokeLinecap="round" />
      {/* head + helmet */}
      <circle cx={104} cy={26} r={10} fill="#f2b98c" />
      <path d="M93 24 A 11 11 0 0 1 115 23 L 93 25 Z" fill="#FF3D14" stroke="#0A0A09" strokeWidth="1.5" />
      <circle cx={109} cy={26} r={1.6} fill="#0A0A09" />
    </svg>
  );
}

/* ---------- scenery bits ---------- */

function Beat({
  x,
  bottom,
  tilt = "0deg",
  kicker,
  children,
}: {
  x: number;
  bottom: number;
  tilt?: string;
  kicker?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="absolute z-10" style={{ left: x, bottom, transform: `rotate(${tilt})` }}>
      {/* cream + tail + kicker: unmistakably speech, never a cloud */}
      <div className="ride-beat relative max-w-[86vw] rounded-2xl border-[3px] border-[#0A0A09] bg-[#FFF9EC] px-6 py-5 text-[18px] font-bold leading-[1.4] tracking-[-0.01em] text-[#0A0A09] shadow-[6px_6px_0_#0A0A09] sm:max-w-[360px] md:max-w-[420px] md:px-7 md:py-6 md:text-[21px]">
        {kicker && (
          <span className="mb-2 inline-block rounded-md bg-[#FF3D14] px-2.5 py-1 font-mono text-[11px] font-bold uppercase tracking-[0.14em] text-white md:text-[12px]">
            {kicker}
          </span>
        )}
        <div>{children}</div>
        <span
          className="absolute -bottom-[13px] left-9 h-6 w-6 rotate-45 border-b-[3px] border-r-[3px] border-[#0A0A09] bg-[#FFF9EC]"
          aria-hidden="true"
        />
      </div>
    </div>
  );
}

function Tree({ x, s = 1 }: { x: number; s?: number }) {
  return (
    <div className="absolute" style={{ left: x, bottom: GROUND_H - 4 }} aria-hidden="true">
      <div style={{ transform: `scale(${s})`, transformOrigin: "bottom" }}>
        <div className="mx-auto h-14 w-14 rounded-full bg-[#3E9B4F]" />
        <div className="mx-auto -mt-2 h-8 w-2.5 bg-[#7A4B2A]" />
      </div>
    </div>
  );
}

function Sheep({ x }: { x: number }) {
  return (
    <div className="absolute text-3xl" style={{ left: x, bottom: GROUND_H - 2 }} aria-hidden="true">
      🐑
    </div>
  );
}

function KmPost({ x, km }: { x: number; km: number }) {
  return (
    <div className="absolute" style={{ left: x, bottom: GROUND_H - 6 }} aria-hidden="true">
      <div className="rounded-sm border-2 border-[#0A0A09] bg-white px-1.5 py-0.5 font-mono text-[10px] font-bold text-[#0A0A09]">
        {km} km
      </div>
      <div className="mx-auto h-5 w-1 bg-[#0A0A09]" />
    </div>
  );
}

/* ---------- main ---------- */

export function RideIntro({ onFinished }: { onFinished?: () => void }) {
  const trackRef = useRef<HTMLDivElement>(null);
  const worldRef = useRef<HTMLDivElement>(null);
  const skyFarRef = useRef<HTMLDivElement>(null);
  const hillsRef = useRef<HTMLDivElement>(null);
  const charRef = useRef<HTMLDivElement>(null);
  const boatRef = useRef<HTMLDivElement>(null);
  const duskRef = useRef<HTMLDivElement>(null);
  const kmRef = useRef<HTMLSpanElement>(null);
  const dayRef = useRef<HTMLSpanElement>(null);
  const barRef = useRef<HTMLDivElement>(null);
  const finaleRef = useRef<HTMLDivElement>(null);
  const whiteoutRef = useRef<HTMLDivElement>(null);
  const hintRef = useRef<HTMLDivElement>(null);
  const [reduced, setReduced] = useState(false);
  const onFinishedRef = useRef(onFinished);
  onFinishedRef.current = onFinished;
  const finishedRef = useRef(false);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setReduced(true);
      finishedRef.current = true;
      onFinishedRef.current?.();
      return;
    }
    let raf = 0;
    let smooth = 0;
    let beats: HTMLElement[] = [];

    /* ground profile: one honest hill before the coast */
    const H0 = 1560, H1 = 1810, H2 = 2060, HILL = 74;
    const groundLift = (x: number) => {
      if (x <= H0 || x >= H2) return 0;
      if (x <= H1) return ((x - H0) / (H1 - H0)) * HILL;
      return (1 - (x - H1) / (H2 - H1)) * HILL;
    };
    const FERRY0 = 2470, FERRY1 = 3130;

    const tick = () => {
      const track = trackRef.current;
      if (track && worldRef.current) {
        const vw = window.innerWidth;
        // Progress against the real scroll container (<main>, which sits
        // below the sticky header) — window-based math can never hit 1.0
        // here, which kept the finish from firing on short viewports.
        const scroller = (track.closest("main") ?? document.documentElement) as HTMLElement;
        const total = Math.max(1, track.offsetHeight - scroller.clientHeight);
        const target = Math.min(1, Math.max(0, scroller.scrollTop / total));
        smooth += (target - smooth) * 0.13;
        if (Math.abs(target - smooth) < 0.0002) smooth = target;

        const charCenterX = vw * 0.16 + 75;
        const maxShift = Math.max(
          0,
          Math.min(WORLD_W - vw, TOWER_ANCHOR - charCenterX)
        );
        const shift = smooth * maxShift;
        worldRef.current.style.transform = `translate3d(${-shift}px,0,0)`;
        if (skyFarRef.current)
          skyFarRef.current.style.transform = `translate3d(${-shift * 0.25}px,0,0)`;
        if (hillsRef.current)
          hillsRef.current.style.transform = `translate3d(${-shift * 0.55}px,0,0)`;

        /* cyclist: fixed x, lifted by the hill, hidden on the ferry */
        const charX = vw * 0.16 + 75;
        const wx = charX + shift;
        const lift = groundLift(wx);
        const onFerry = wx > FERRY0 && wx < FERRY1;
        if (charRef.current) {
          const slope =
            wx > H0 && wx < H1 ? -7 : wx > H1 && wx < H2 ? 7 : 0;
          charRef.current.style.transform = `translateY(${-lift}px) rotate(${slope}deg)`;
          charRef.current.style.opacity = onFerry ? "0" : "1";
          charRef.current.classList.toggle(
            "moving",
            Math.abs(target - smooth) > 0.0004
          );
        }
        if (boatRef.current) boatRef.current.style.opacity = onFerry ? "1" : "0";

        /* dusk falls in France */
        if (duskRef.current) {
          const d = Math.max(0, Math.min(0.55, (smooth - 0.62) * 2.2));
          duskRef.current.style.opacity = String(d);
        }

        /* HUD */
        if (kmRef.current)
          kmRef.current.textContent = String(Math.round(TRIP_KM * smooth));
        if (dayRef.current)
          dayRef.current.textContent = String(Math.min(4, 1 + Math.floor(smooth * 4)));
        if (barRef.current) barRef.current.style.width = `${smooth * 100}%`;
        if (hintRef.current)
          hintRef.current.style.opacity = smooth > 0.03 ? "0" : "1";

        /* finale */
        if (finaleRef.current) {
          const f = Math.max(0, Math.min(1, (smooth - 0.93) / 0.05));
          finaleRef.current.style.opacity = String(f);
          finaleRef.current.classList.toggle("celebrate", f > 0.6);
        }
        if (!finishedRef.current && smooth >= 0.985) {
          finishedRef.current = true;
          onFinishedRef.current?.();
        }

        /* dissolve to white over the last stretch so the un-pin into the
           page below is seamless instead of a hard cut */
        if (whiteoutRef.current) {
          const w = Math.max(0, Math.min(1, (smooth - 0.9) / 0.1));
          whiteoutRef.current.style.opacity = String(w * w);
        }

        /* beat pop-ins */
        if (!beats.length)
          beats = Array.from(track.querySelectorAll<HTMLElement>(".ride-beat"));
        for (const el of beats) {
          if (!el.classList.contains("in")) {
            const r = el.getBoundingClientRect();
            if (r.left < vw * 0.9 && r.right > 0) el.classList.add("in");
          }
        }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  const skip = () => {
    const track = trackRef.current;
    const main = track?.closest("main");
    if (track && main)
      main.scrollTo({ top: track.offsetTop + track.offsetHeight - window.innerHeight + 1, behavior: "smooth" });
  };

  if (reduced) return null;

  return (
    <div ref={trackRef} className="relative h-[520vh]">
      <div
        className="sticky top-0 h-screen overflow-hidden"
        style={{ background: "linear-gradient(#BFE0F7, #E6F3FC 62%, #F2F9FE)" }}
      >
        {/* sun */}
        <div
          className="absolute right-[8%] top-10 h-16 w-16 rounded-full bg-[#FFD166]"
          style={{ boxShadow: "0 0 46px rgba(255,209,102,0.85)" }}
          aria-hidden="true"
        />

        {/* far clouds */}
        <div ref={skyFarRef} className="absolute inset-0 will-change-transform" style={{ width: WORLD_W }} aria-hidden="true">
          {[300, 1100, 1900, 2800, 3700, 4600, 5500, 6400, 7300, 8200].map((x, i) => (
            <div
              key={x}
              className="absolute rounded-full bg-white/90"
              style={{
                left: x,
                top: 60 + (i % 3) * 46,
                width: 110,
                height: 32,
                boxShadow: "22px 10px 0 rgba(255,255,255,0.85), -20px 12px 0 rgba(255,255,255,0.8)",
              }}
            />
          ))}
        </div>

        {/* mid hills */}
        <div ref={hillsRef} className="absolute inset-0 will-change-transform" style={{ width: WORLD_W }} aria-hidden="true">
          {[
            { x: 100, w: 520, h: 130, c: "#CDE8C9" },
            { x: 900, w: 640, h: 170, c: "#B9DFB4" },
            { x: 1900, w: 520, h: 120, c: "#CDE8C9" },
            { x: 3300, w: 680, h: 160, c: "#B9DFB4" },
            { x: 4400, w: 560, h: 130, c: "#CDE8C9" },
            { x: 5300, w: 640, h: 150, c: "#B9DFB4" },
            { x: 6400, w: 560, h: 130, c: "#CDE8C9" },
            { x: 7400, w: 640, h: 160, c: "#B9DFB4" },
          ].map((h) => (
            <div
              key={h.x}
              className="absolute rounded-t-full"
              style={{ left: h.x, bottom: GROUND_H - 8, width: h.w, height: h.h, backgroundColor: h.c }}
            />
          ))}
        </div>

        {/* world */}
        <div ref={worldRef} className="absolute inset-0 z-10 will-change-transform" style={{ width: WORLD_W }}>
          {/* ground with the painted route */}
          <div
            className="absolute bottom-0"
            style={{
              width: WORLD_W,
              height: GROUND_H,
              background:
                "linear-gradient(#69B578 0 12px, #E8E3D8 12px 16px, #DCD5C6 16px 100%)",
              borderTop: "3px solid #0A0A09",
            }}
            aria-hidden="true"
          >
            <div
              className="absolute inset-x-0 top-[44px] h-[3px]"
              style={{
                background:
                  "repeating-linear-gradient(90deg, #FF3D14 0 26px, transparent 26px 52px)",
              }}
            />
          </div>
          {/* water for the ferry crossing (covers the ground) */}
          <div
            className="absolute bottom-0 z-10"
            style={{
              left: 2400,
              width: 800,
              height: GROUND_H + 2,
              background: "linear-gradient(#8FC9E8, #5FA8D3)",
              borderTop: "3px solid #0A0A09",
            }}
            aria-hidden="true"
          />

          {/* LONDON */}
          <div className="absolute" style={{ left: 90, bottom: GROUND_H }} aria-hidden="true">
            <div className="flex items-end gap-2 opacity-80">
              <div className="h-40 w-16 bg-[#41506B]" />
              <div className="relative h-64 w-12 bg-[#4A5A78]">
                <div className="absolute left-1/2 top-8 h-8 w-8 -translate-x-1/2 rounded-full border-4 border-[#F2E9D8] bg-[#2E3A52]" />
                <div className="absolute -top-9 left-1/2 h-0 w-0 -translate-x-1/2 border-x-[24px] border-b-[36px] border-x-transparent border-b-[#4A5A78]" />
              </div>
              <div className="h-32 w-20 bg-[#41506B]" />
            </div>
          </div>
          <Beat x={320} bottom={GROUND_H + 150} tilt="-1.4deg" kicker="The brief">
            “London to Paris in May. Pubs over pace.”{" "}
            <span className="text-[#FF3D14]">That&apos;s all it needs.</span>
          </Beat>

          <Tree x={760} s={0.9} />
          <KmPost x={860} km={40} />
          <Sheep x={1010} />
          <Sheep x={1120} />

          {/* WEATHER beat — a cloud with real receipts */}
          <div className="absolute" style={{ left: 1240, bottom: GROUND_H + 190 }} aria-hidden="true">
            <div className="relative">
              <div className="h-12 w-32 rounded-full bg-[#9FB4C4]" style={{ boxShadow: "18px 8px 0 #B7C8D5, -14px 8px 0 #B7C8D5" }} />
              {[8, 34, 60, 86].map((rx, i) => (
                <span key={rx} className="rain-drop absolute h-4 w-0.5 bg-[#5FA8D3]" style={{ left: rx, top: 52, animationDelay: `${i * 0.18}s` }} />
              ))}
            </div>
          </div>
          <Beat x={1290} bottom={GROUND_H + 240} tilt="1.1deg" kicker="Weather check">
            It checked <span className="text-[#FF3D14]">30 years of May weather</span>.
            Pack for one wet morning — Day 2, probably.
          </Beat>

          {/* THE HILL — visible ramp the cyclist climbs */}
          <svg
            className="absolute"
            style={{ left: 1560, bottom: GROUND_H - 2 }}
            width={500}
            height={80}
            viewBox="0 0 500 80"
            aria-hidden="true"
          >
            <path d="M0 80 L250 6 L500 80 Z" fill="#DCD5C6" stroke="#0A0A09" strokeWidth="3" />
            <path d="M0 80 L250 6 L500 80" fill="none" stroke="#FF3D14" strokeWidth="3" strokeDasharray="14 12" />
          </svg>
          <Beat x={1620} bottom={GROUND_H + 175} tilt="-1deg" kicker="Climb detected">
            It <span className="text-[#FF3D14]">felt this hill</span> in the elevation
            data — and split the day early because of it.
          </Beat>
          <KmPost x={2200} km={120} />

          {/* CLIFFS + FERRY */}
          <div className="absolute" style={{ left: 2330, bottom: GROUND_H - 2 }} aria-hidden="true">
            <div className="h-24 w-16 border-2 border-[#0A0A09] bg-white" style={{ clipPath: "polygon(0 0, 100% 0, 78% 100%, 0 100%)" }} />
          </div>
          <Beat x={2560} bottom={GROUND_H + 170} tilt="1.3deg" kicker="Ferry logged">
            Newhaven → Dieppe. The ferry is{" "}
            <span className="text-[#FF3D14]">already in the plan</span> — timed,
            priced, sanity-checked.
          </Beat>

          {/* FRANCE */}
          <div className="absolute" style={{ left: 3260, bottom: GROUND_H + 4 }} aria-hidden="true">
            <div className="rounded-md border-2 border-[#0A0A09] bg-white px-3 py-1.5 font-mono text-[11px] font-bold tracking-[0.12em] text-[#0A0A09]">
              FRANCE →
            </div>
            <div className="mx-auto h-6 w-1 bg-[#0A0A09]" />
          </div>
          {[3450, 3560, 3670, 3780, 3890].map((x) => (
            <div key={x} className="absolute" style={{ left: x, bottom: GROUND_H - 2 }} aria-hidden="true">
              <div className="h-10 w-16 rounded-t-md border-2 border-[#2E6B3A] bg-[#4C8F5C]" />
            </div>
          ))}
          <KmPost x={4150} km={250} />

          {/* THE AUBERGE */}
          <div className="absolute" style={{ left: 4560, bottom: GROUND_H - 2 }} aria-hidden="true">
            <div className="relative h-32 w-44 border-[3px] border-[#0A0A09] bg-[#F6EFE3]">
              <div className="absolute -top-12 left-1/2 h-0 w-0 -translate-x-1/2 border-x-[92px] border-b-[48px] border-x-transparent border-b-[#B4472F]" />
              {[10, 62, 114].map((wx) => (
                <div key={wx} className="absolute top-5 h-8 w-7 border-2 border-[#0A0A09] bg-[#FFD166]" style={{ left: wx, boxShadow: "0 0 14px rgba(255,209,102,0.8)" }} />
              ))}
              <div className="absolute bottom-0 left-1/2 h-14 w-9 -translate-x-1/2 border-2 border-b-0 border-[#0A0A09] bg-[#7A4B2A]" />
            </div>
          </div>
          <Beat x={4620} bottom={GROUND_H + 235} tilt="-1.2deg" kicker="Bed booked">
            Tonight: <span className="text-[#FF3D14]">4.7★, big breakfast, safe
            bike shed</span>. Spaced exactly to your legs.
          </Beat>

          {/* PARIS */}
          <svg className="absolute" style={{ left: 5450, bottom: GROUND_H - 2 }} width={260} height={340} viewBox="0 0 260 340" aria-hidden="true">
            <path d="M130 8 L96 210 L20 336 M130 8 L164 210 L240 336" fill="none" stroke="#3B3B47" strokeWidth="10" strokeLinecap="round" />
            <path d="M96 210 L164 210 M74 268 L186 268 M108 120 L152 120" stroke="#3B3B47" strokeWidth="8" strokeLinecap="round" />
            <path d="M96 210 Q 130 250 164 210 M74 268 Q 130 320 186 268" fill="none" stroke="#3B3B47" strokeWidth="6" />
          </svg>
          <KmPost x={5380} km={364} />
          {/* Paris rooftops beyond the tower */}
          {[
            { x: 5800, w: 150, h: 120 },
            { x: 5980, w: 120, h: 150 },
            { x: 6130, w: 170, h: 110 },
            { x: 6330, w: 130, h: 140 },
            { x: 6490, w: 160, h: 115 },
          ].map((b) => (
            <div key={b.x} className="absolute" style={{ left: b.x, bottom: GROUND_H - 2 }} aria-hidden="true">
              <div
                className="border-2 border-[#0A0A09]/30 bg-[#D9CDBE]"
                style={{ width: b.w, height: b.h }}
              >
                <div className="grid grid-cols-4 gap-1.5 p-2">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <div key={i} className="h-3 rounded-[1px] bg-[#8E7F6C]/50" />
                  ))}
                </div>
              </div>
              <div
                className="absolute -top-4 left-0 h-4 w-full bg-[#5E6B7A]"
                style={{ clipPath: "polygon(0 100%, 6% 0, 94% 0, 100% 100%)" }}
              />
            </div>
          ))}
        </div>

        {/* the ferry (fixed like the cyclist, shown over water) */}
        <div
          ref={boatRef}
          className="absolute z-20 transition-opacity duration-300"
          style={{ left: "13vw", bottom: GROUND_H - 14, opacity: 0 }}
          aria-hidden="true"
        >
          <div className="boat-bob">
            <div className="ml-16 text-4xl">🚴</div>
            <div className="flex h-14 w-64 items-center justify-center rounded-b-[30px] border-[3px] border-[#0A0A09] bg-[#F2F2EF] font-mono text-[10px] font-bold tracking-[0.2em] text-[#0A0A09]">
              DIEPPE FERRIES
            </div>
          </div>
        </div>

        {/* the cyclist */}
        <div ref={charRef} className="absolute z-20" style={{ left: "16vw", bottom: GROUND_H - 8 }}>
          <div className="ride-cyclist relative" style={{ width: 150, height: 112 }}>
            <div className="cyclist-a absolute inset-0">
              <Cyclist frame="a" />
            </div>
            <div className="cyclist-b absolute inset-0">
              <Cyclist frame="b" />
            </div>
          </div>
        </div>

        {/* dusk wash */}
        <div
          ref={duskRef}
          className="pointer-events-none absolute inset-0 z-20"
          style={{
            opacity: 0,
            background: "linear-gradient(rgba(74,42,110,0.55), rgba(255,110,60,0.35) 70%, transparent)",
          }}
          aria-hidden="true"
        />

        {/* HUD */}
        <div className="absolute inset-x-0 top-0 z-30 flex items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <div className="hidden rounded-lg border-2 border-[#0A0A09] bg-white px-3 py-2 font-mono text-[12px] font-bold tracking-[0.12em] text-[#0A0A09] sm:block">
            LONDON → PARIS
          </div>
          <div className="hidden min-w-0 flex-1 sm:block">
            <div className="h-2.5 w-full overflow-hidden rounded-full border-2 border-[#0A0A09] bg-white">
              <div ref={barRef} className="h-full bg-[#FF3D14]" style={{ width: "0%" }} />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="rounded-lg border-2 border-[#0A0A09] bg-white px-3 py-2 font-mono text-[11px] font-bold tracking-[0.08em] text-[#0A0A09] sm:text-[12px]">
              <span ref={kmRef}>0</span>/{TRIP_KM} km · DAY <span ref={dayRef}>1</span>
            </div>
            <button
              type="button"
              onClick={skip}
              className="rounded-lg border-2 border-[#0A0A09] bg-[#FFD166] px-3 py-2 font-mono text-[11px] font-bold tracking-[0.08em] text-[#0A0A09] transition-colors hover:bg-[#FF3D14] hover:text-white sm:text-[12px]"
            >
              SKIP THE RIDE ▸
            </button>
          </div>
        </div>

        {/* scroll hint */}
        <div ref={hintRef} className="pointer-events-none absolute inset-x-0 top-24 z-30 text-center transition-opacity duration-500">
          <span className="ride-hint inline-block rounded-full border-2 border-[#0A0A09] bg-white px-5 py-2.5 text-[15px] font-bold text-[#0A0A09]">
            ▼ Scroll to start pedalling ▼
          </span>
        </div>

        {/* seamless hand-off into the page below */}
        <div
          ref={whiteoutRef}
          className="pointer-events-none absolute inset-0 z-50"
          style={{
            opacity: 0,
            background: "linear-gradient(rgba(255,255,255,0) 0%, rgba(255,255,255,0.9) 55%, #ffffff 100%)",
          }}
          aria-hidden="true"
        />

        {/* finale */}
        <div
          ref={finaleRef}
          className="absolute inset-0 z-40 flex items-center justify-center"
          style={{ opacity: 0, pointerEvents: "none" }}
        >
          <div className="confetti-box absolute inset-0 overflow-hidden" aria-hidden="true">
            {Array.from({ length: 24 }).map((_, i) => (
              <span
                key={i}
                className="confetti absolute top-[-4%] block h-3 w-1.5 rounded-sm"
                style={{
                  left: `${(i * 41) % 100}%`,
                  backgroundColor: ["#FF3D14", "#FFD166", "#1D4FB0", "#3E9B4F", "#9B5DE5"][i % 5],
                  animationDelay: `${(i % 8) * 0.35}s`,
                  animationDuration: `${2.6 + (i % 5) * 0.4}s`,
                }}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
