"use client";

/**
 * The obsession board — the landing's story section. Leans into the
 * Cyclepath/psychopath pun: an evidence board of the very real data the
 * agent obsesses over, connected by orange string, ending in a CTA that
 * drops the visitor straight into the chat input below.
 */

const EVIDENCE = [
  {
    title: "Routes: actual bike paths",
    body: "BRouter routing — canal towpaths and voies vertes, not A-roads.",
    tilt: "-1.4deg",
  },
  {
    title: "Weather: 30-year receipts",
    body: "ECMWF climate norms for your exact week. Not a vibes forecast.",
    tilt: "1.1deg",
  },
  {
    title: "Sleep: vetted stops",
    body: "Real places with ratings, photos and sane prices — spaced to your legs.",
    tilt: "-0.9deg",
  },
  {
    title: "Ferries: priced. Twice.",
    body: "Crossings, trains and awkward logistics folded into the day-by-day.",
    tilt: "1.3deg",
  },
];

const STEPS = [
  {
    n: "01",
    title: "Say the dream",
    body: "“London to Paris in May. Pubs over pace.” That's enough.",
  },
  {
    n: "02",
    title: "Watch it obsess",
    body: "Routes, weather and overnight stops stream in live — you can even watch it think.",
  },
  {
    n: "03",
    title: "Ride out",
    body: "A day-by-day plan with maps and GPX files for your bike computer.",
  },
];

function focusChat() {
  const el = document.querySelector<HTMLTextAreaElement>("textarea");
  el?.focus();
  el?.scrollIntoView({ behavior: "smooth", block: "center" });
}

export function ObsessionBoard() {
  return (
    <section aria-label="How Cyclepath works" className="mt-20 sm:mt-28">
      {/* board header */}
      <h2 className="max-w-[22ch] text-[30px] font-bold leading-[1.05] tracking-[-0.03em] text-foreground sm:text-[40px]">
        It plans your trip like it&apos;s a{" "}
        <span className="text-primary">conspiracy</span>.
      </h2>
      <p className="mt-3 max-w-[52ch] text-[15px] leading-[1.6] text-muted-foreground sm:text-[16px]">
        Red-string energy, real data. Four things it refuses to guess about:
      </p>

      {/* evidence board */}
      <div className="relative mt-10">
        {/* the string */}
        <svg
          className="pointer-events-none absolute inset-x-0 top-1/2 hidden h-24 w-full -translate-y-1/2 lg:block"
          viewBox="0 0 1200 100"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <path
            d="M 20 55 C 180 -10, 320 110, 480 45 S 800 90, 940 35 S 1140 70, 1185 40"
            fill="none"
            stroke="#FF3D14"
            strokeWidth="2"
            strokeDasharray="6 7"
            className="string-draw"
          />
        </svg>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {EVIDENCE.map((e) => (
            <div
              key={e.title}
              className="board-card relative rounded-xl border border-border bg-card p-5 shadow-sm"
              style={{ transform: `rotate(${e.tilt})` }}
            >
              {/* pin */}
              <span
                className="absolute -top-1.5 left-1/2 h-3 w-3 -translate-x-1/2 rounded-full border-2 border-background bg-primary shadow-sm"
                aria-hidden="true"
              />
              <h3 className="text-[15px] font-semibold tracking-[-0.01em] text-foreground">
                {e.title}
              </h3>
              <p className="mt-2 text-[13px] leading-[1.55] text-muted-foreground">
                {e.body}
              </p>
            </div>
          ))}
        </div>

        {/* the self-critique note */}
        <div className="mt-6 rounded-xl border-l-4 border-primary bg-secondary px-5 py-4">
          <p className="text-[14px] leading-[1.6] text-foreground">
            <span className="font-semibold">
              Then it interrogates its own plan.
            </span>{" "}
            A self-critique loop re-checks distances, gaps and claims before
            you ever see them — it catches its mistakes so you don&apos;t have
            to.
          </p>
        </div>
      </div>

      {/* how it goes */}
      <div className="mt-14 grid grid-cols-1 gap-6 sm:grid-cols-3">
        {STEPS.map((s) => (
          <div key={s.n}>
            <span className="font-mono text-[11px] font-medium tracking-[0.14em] text-primary">
              {s.n}
            </span>
            <h3 className="mt-1.5 text-[17px] font-semibold tracking-[-0.01em] text-foreground">
              {s.title}
            </h3>
            <p className="mt-1.5 text-[13.5px] leading-[1.6] text-muted-foreground">
              {s.body}
            </p>
          </div>
        ))}
      </div>

      {/* CTA */}
      <div className="mt-12 flex flex-wrap items-center gap-4">
        <button
          type="button"
          onClick={focusChat}
          className="rounded-lg bg-primary px-6 py-3.5 text-[15px] font-semibold text-primary-foreground transition-transform hover:-translate-y-0.5 hover:shadow-lg"
        >
          Talk to the Cyclepath →
        </button>
        <span className="text-[13px] text-muted-foreground">
          No signup. Just tell it where you want to ride — or pick a curated
          route below.
        </span>
      </div>
    </section>
  );
}
