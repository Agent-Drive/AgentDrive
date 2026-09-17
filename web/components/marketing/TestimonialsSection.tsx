const TESTIMONIALS = [
  {
    quote:
      "“Agent Drive cut our competitive research time in half. We actually know what’s working in market before we brief creative.”",
    initials: "SC",
    name: "Sarah Chen",
    role: "Head of Growth",
    logo: "Ogilvy",
  },
  {
    quote:
      "“The corpus quality is unlike anything else we’ve used. Our copy agents finally have real signal to draw from.”",
    initials: "MW",
    name: "Marcus Webb",
    role: "AI Lead",
    logo: "Monks",
  },
  {
    quote:
      "“Clean API, honest docs, fast support. Rare for a data product at this stage. We’re building our entire intel stack on it.”",
    initials: "PN",
    name: "Priya Nair",
    role: "Strategy Director",
    logo: "TBWA",
  },
] as const;

export function TestimonialsSection() {
  return (
    <section>
      <span className="mb-6 block font-mono text-[0.68rem] tracking-widest text-[var(--ink-dim)] uppercase">
        What people are saying
      </span>
      <div className="testimonial-grid">
        {TESTIMONIALS.map((item) => (
          <div key={item.name} className="testimonial-item">
            <p className="testimonial-quote">{item.quote}</p>
            <div className="testimonial-meta">
              <div className="testimonial-avatar">{item.initials}</div>
              <div>
                <div className="testimonial-name">{item.name}</div>
                <div className="testimonial-role">{item.role}</div>
              </div>
              <span className="testimonial-logo">{item.logo}</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
