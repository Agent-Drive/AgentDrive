import { MarginNote } from "./MarginNote";
import { PullQuote } from "./PullQuote";

export function FeaturedArticle() {
  return (
    <article className="article-body font-geist">
      <p>
        Most AI outputs are only as good as the data behind them. We&apos;re building the layer
        that fixes that — one domain at a time. The problem with general-purpose models isn&apos;t
        their reasoning; it&apos;s their lack of grounded, specific context.
      </p>

      <p id="why-marketing-copy-fails">
        When you ask a model to write an ad, it defaults to what it knows: a bland, average
        amalgamation of every piece of text it scraped from the internet up until its training
        cutoff. It doesn&apos;t know what&apos;s trending on TikTok today, or what copy structure is
        actually converting for DTC apparel brands right now.
      </p>

      <div className="relative-block" id="building-the-corpus">
        <p>
          We go deep on one domain before the next. Our first dataset, Ads, gives you a live view
          of what competitors are running — and gives your agents real market copy to work with at
          generation time.
        </p>
        <MarginNote title="Note on schema:">
          The v2.0 Ads Dataset includes normalized brand slugs, full ad body text, call to actions,
          and exact CDN asset URLs.
        </MarginNote>
      </div>

      <PullQuote>
        &ldquo;Agents retrieve real ad context at generation time — so output is accurate,
        grounded, and on-brand.&rdquo;
      </PullQuote>

      <h2 id="the-generalization-trap">The generalization trap</h2>

      <p>
        Three surfaces. One data layer. Whether you&apos;re accessing via MCP for Claude, hitting
        our REST API, or pulling via CLI, the goal is the same: inject high-fidelity context into
        your workflows.
      </p>

      <div className="relative-block">
        <p>
          Consider the typical agent workflow without Agent Drive. An agent is prompted to
          &ldquo;write a Facebook ad for running shoes.&rdquo; It hallucinates a generic benefit
          statement and a tired hook.
        </p>
        <MarginNote>
          <span className="mb-2 block">
            In testing, agents with access to our live corpus produced copy that human editors
            rated 3x more &ldquo;market-ready&rdquo; than zero-shot generation.
          </span>
        </MarginNote>
      </div>

      <p>
        With Agent Drive, that same agent first queries the live database:{" "}
        <code>agentdrive pull --brand nike --limit 50</code>. It analyzes current hooks, identifies
        the prevailing tone for summer campaigns, and generates a variant grounded in reality.
      </p>

      <div className="section-break" />

      <h2 id="what-people-are-saying">What people are saying</h2>

      <p>
        The reception from early partners has validated this approach. Marcus Webb, AI Lead at
        Monks, noted that &ldquo;The corpus quality is unlike anything else we&apos;ve used. Our
        copy agents finally have real signal to draw from.&rdquo;
      </p>

      <p>
        Similarly, Sarah Chen at Ogilvy mentioned it cut their competitive research time in half,
        allowing them to know what&apos;s working in market before briefing creative. This
        duality—serving both humans who need intelligence and agents who need context—is the core
        of Agent Drive.
      </p>
    </article>
  );
}
