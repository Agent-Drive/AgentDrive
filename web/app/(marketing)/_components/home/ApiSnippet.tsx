"use client";

import { useState } from "react";

type Pane = "request" | "response" | "schema";

const TABS: { id: Pane; label: string }[] = [
  { id: "request", label: "Request" },
  { id: "response", label: "Response" },
  { id: "schema", label: "Schema" },
];

const API_URL = "https://api.agentdrive.so/v1/ads";

export function ApiSnippet() {
  const [pane, setPane] = useState<Pane>("request");

  return (
    <div className="api-snippet">
      <div className="api-snippet-bar" style={{ paddingBottom: 0 }}>
        <span className="api-dot" style={{ background: "#ff5f57" }} />
        <span className="api-dot" style={{ background: "#febc2e" }} />
        <span className="api-dot" style={{ background: "#28c840" }} />
        <div className="api-tabs" style={{ marginLeft: "0.75rem", flex: 1, borderBottom: "none" }}>
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`api-tab${pane === tab.id ? " active" : ""}`}
              onClick={() => setPane(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className={`api-pane${pane === "request" ? " active" : ""}`}>
        <pre>
          <span className="token-comment"># Retrieve competitor ads by brand</span>
          {"\n"}
          <span className="token-method">curl</span>{" "}
          <span className="token-url">{API_URL}</span>{" "}
          <span className="token-param">\</span>
          {"\n"}
          {"  -H "}
          <span className="token-val">&quot;Authorization: Bearer &lt;token&gt;&quot;</span>{" "}
          <span className="token-param">\</span>
          {"\n"}
          {"  -d "}
          <span className="token-key">brand</span>=<span className="token-val">&quot;nike&quot;</span>{" "}
          <span className="token-param">\</span>
          {"\n"}
          {"  -d "}
          <span className="token-key">format</span>=
          <span className="token-val">&quot;video,image&quot;</span>{" "}
          <span className="token-param">\</span>
          {"\n"}
          {"  -d "}
          <span className="token-key">limit</span>=<span className="token-val">50</span>
        </pre>
      </div>

      <div className={`api-pane${pane === "response" ? " active" : ""}`}>
        <pre>
          <span className="token-comment"># 200 OK — structured ad object</span>
          {"\n"}
          <span className="token-key">{"{"}</span>
          {"\n"}
          {"  "}
          <span className="token-key">&quot;id&quot;</span>:{" "}
          <span className="token-val">&quot;ad_8xkP2mNv&quot;</span>,
          {"\n"}
          {"  "}
          <span className="token-key">&quot;brand&quot;</span>:{" "}
          <span className="token-val">&quot;nike&quot;</span>,
          {"\n"}
          {"  "}
          <span className="token-key">&quot;copy&quot;</span>:{" "}
          <span className="token-val">&quot;Just Do It. Summer Edition.&quot;</span>,
          {"\n"}
          {"  "}
          <span className="token-key">&quot;hook&quot;</span>:{" "}
          <span className="token-val">&quot;Built for the heat.&quot;</span>,
          {"\n"}
          {"  "}
          <span className="token-key">&quot;cta&quot;</span>:{" "}
          <span className="token-val">&quot;Shop Now&quot;</span>,
          {"\n"}
          {"  "}
          <span className="token-key">&quot;platform&quot;</span>:{" "}
          <span className="token-val">&quot;meta&quot;</span>,
          {"\n"}
          {"  "}
          <span className="token-key">&quot;format&quot;</span>:{" "}
          <span className="token-val">&quot;video&quot;</span>,
          {"\n"}
          {"  "}
          <span className="token-key">&quot;first_seen&quot;</span>:{" "}
          <span className="token-val">&quot;2025-06-01&quot;</span>,
          {"\n"}
          {"  "}
          <span className="token-key">&quot;creative_url&quot;</span>:{" "}
          <span className="token-val">&quot;https://cdn.agentdrive.so/…&quot;</span>
          {"\n"}
          <span className="token-key">{"}"}</span>
        </pre>
      </div>

      <div className={`api-pane${pane === "schema" ? " active" : ""}`}>
        <pre>
          <span className="token-comment"># Ad object schema (TypeScript)</span>
          {"\n"}
          <span className="token-key">type</span> <span className="token-url">Ad</span>{" "}
          <span className="token-param">=</span> <span className="token-key">{"{"}</span>
          {"\n"}
          {"  id:           "}
          <span className="token-val">string</span>
          {"       "}
          <span className="token-comment">// unique ad identifier</span>
          {"\n"}
          {"  brand:        "}
          <span className="token-val">string</span>
          {"       "}
          <span className="token-comment">// normalized brand slug</span>
          {"\n"}
          {"  copy:         "}
          <span className="token-val">string</span>
          {"       "}
          <span className="token-comment">// full ad body text</span>
          {"\n"}
          {"  hook:         "}
          <span className="token-val">string</span>
          {"       "}
          <span className="token-comment">// opening line / hook</span>
          {"\n"}
          {"  cta:          "}
          <span className="token-val">string</span>
          {"       "}
          <span className="token-comment">// call to action text</span>
          {"\n"}
          {"  platform:     "}
          <span className="token-val">Platform</span>
          {"     "}
          <span className="token-comment">// meta | tiktok | youtube</span>
          {"\n"}
          {"  format:       "}
          <span className="token-val">Format</span>
          {"       "}
          <span className="token-comment">// video | image | carousel</span>
          {"\n"}
          {"  first_seen:   "}
          <span className="token-val">ISODate</span>
          {"      "}
          <span className="token-comment">// when first observed</span>
          {"\n"}
          {"  creative_url: "}
          <span className="token-val">string</span>
          {"       "}
          <span className="token-comment">// CDN asset URL</span>
          {"\n"}
          <span className="token-key">{"}"}</span>
        </pre>
      </div>
    </div>
  );
}
