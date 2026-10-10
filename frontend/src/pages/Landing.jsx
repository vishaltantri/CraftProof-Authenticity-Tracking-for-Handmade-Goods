import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Tag, BadgeCheck, Search, Brush, ArrowLeftRight, Globe, Hammer, Building2,
  Printer, TrendingUp, ListChecks, ScrollText, Quote, ShieldCheck,
  ArrowRight, ScanLine, User, Lock, AlertTriangle, Stamp,
} from 'lucide-react'
import './landing.css'

const SAMPLE_CODES = [
  { code: 'KOODE0LL', title: 'Speckled tea bowls' },
  { code: '0275UKUB', title: 'Walnut serving board' },
]

// The mock certificate shown in the hero — mirrors the real certificate page.
const HERO_TIMELINE = [
  { title: 'Crafted in Studio', date: '12 Oct 2024', sub: 'Meera Krishnan', who: 'Confirmed by maker', tone: '' },
  { title: 'Transferred to Gallery', date: '04 Nov 2024', sub: 'Kalakriti Gallery', who: 'Confirmed by gallery', tone: 'cpl-ev-secondary' },
  { title: 'Acquired by Collector', date: '18 Jan 2025', sub: 'Jonathan Price', who: 'Confirmed by collector', tone: 'cpl-ev-success' },
]

function Header() {
  return (
    <header className="cpl-header">
      <div className="cpl-header-inner">
        <Link to="/" className="cpl-brand">
          <Tag size={26} strokeWidth={1.8} aria-hidden="true" />
          <span>CraftProof</span>
        </Link>
        <nav className="cpl-nav" aria-label="Primary">
          <Link to="/how-it-works">How it Works</Link>
          <Link to="/ledger">Public Ledger</Link>
          <a href="#verify">Verify</a>
          <a href="#makers">Makers &amp; Galleries</a>
        </nav>
        <div className="cpl-header-actions">
          <Link to="/signup" className="cpl-btn cpl-btn-ink">Sign up</Link>
          <span className="cpl-avatar" aria-hidden="true"><User size={17} /></span>
        </div>
      </div>
    </header>
  )
}

function Hero() {
  return (
    <section className="cpl-section cpl-hero">
      <div className="cpl-hero-intro">
        <div className="cpl-pill">
          <span className="cpl-pill-dot" aria-hidden="true" />
          <span>Sealed in the public ledger · Tamper-evident provenance</span>
        </div>
        <h1 className="cpl-display">Authenticity you can hold.</h1>
        <p className="cpl-body-lg">
          CraftProof lets you prove a handmade piece is genuine, and see its full
          ownership history — from the maker's hands to yours.
        </p>
      </div>

      <div className="cpl-hero-grid">
        {/* Physical artifact + placard overlay */}
        <div className="cpl-hero-physical">
          <div className="cpl-hero-photo">
            <img
              src="/hero-vessel.jpg"
              alt="Handcrafted raku vase on an artisan workshop bench next to its CraftProof certificate tag with QR code"
            />
            <div className="cpl-placard-overlay">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Tag size={22} strokeWidth={1.8} style={{ color: 'var(--cpl-terracotta)' }} aria-hidden="true" />
                <div>
                  <p className="cpl-placard-title">Physical studio placard attached</p>
                  <p className="cpl-code cpl-placard-sub">Tag 08 · Raku Vessel No. 14</p>
                </div>
              </div>
              <span className="cpl-scan-chip">Physical scan ready</span>
            </div>
          </div>
        </div>

        {/* Digital certificate card */}
        <div className="cpl-hero-cert">
          <div className="cpl-cert">
            <div className="cpl-cert-head">
              <div>
                <span className="cpl-cert-eyebrow">Official Archival Certificate</span>
                <h2 className="cpl-headline-sm" style={{ lineHeight: 1.3 }}>Ember &amp; Ash Raku Vessel No. 14</h2>
                <p className="cpl-body-sm cpl-cert-maker">Meera Krishnan · Ceramicist</p>
              </div>
              <div className="cpl-cert-seal"><BadgeCheck size={20} aria-hidden="true" /></div>
            </div>

            <div className="cpl-cert-badge">
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
                <BadgeCheck size={18} aria-hidden="true" />
                <span className="cpl-badge-label">VERIFIED AUTHENTIC</span>
              </span>
              <span className="cpl-badge-state">State: Intact</span>
            </div>

            <div className="cpl-cert-id">
              <span className="cpl-id-label">Certificate ID</span>
              <span className="cpl-code cpl-id-value">KOODE0LL</span>
            </div>

            <div>
              <span className="cpl-timeline-label">Ownership History (Chain of Custody)</span>
              <div className="cpl-mini-timeline">
                {HERO_TIMELINE.map(ev => (
                  <div key={ev.title} className={`cpl-mini-event ${ev.tone}`}>
                    <div className="cpl-mini-event-row">
                      <span className="cpl-mini-event-title">{ev.title}</span>
                      <span className="cpl-mini-event-date">{ev.date}</span>
                    </div>
                    <p className="cpl-mini-event-sub">
                      {ev.sub} <strong>✓ {ev.who}</strong>
                    </p>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ paddingTop: '0.25rem' }}>
              <Link to="/c/KOODE0LL" className="cpl-btn cpl-btn-ink cpl-btn-block">
                <span>Inspect live certificate</span>
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function VerifyCard() {
  const [code, setCode] = useState('')
  const navigate = useNavigate()

  const handleVerify = () => {
    const trimmed = code.trim().toUpperCase()
    if (trimmed) navigate(`/c/${trimmed}`)
  }

  return (
    <section className="cpl-band cpl-band-tint" id="verify">
      <div className="cpl-band-inner">
        <div className="cpl-verify-card">
          <div className="cpl-verify-head">
            <div>
              <span className="cpl-verify-eyebrow">
                <ShieldCheck size={18} aria-hidden="true" />
                Instant Registry Lookup
              </span>
              <h3 className="cpl-headline-md">Verify a Piece in 5 Seconds</h3>
            </div>
            <span className="cpl-scan-chip-lg cpl-body-sm">
              <ScanLine size={18} aria-hidden="true" />
              Camera scan compatible
            </span>
          </div>

          <p className="cpl-body-md cpl-verify-lede">
            Scan the QR code on the item with any phone camera — no app required.
            Or enter the 8-character certificate code stamped on the physical placard:
          </p>

          <div className="cpl-verify-form">
            <div className="cpl-verify-field">
              <Search size={20} aria-hidden="true" />
              <input
                className="cpl-verify-input"
                type="text"
                inputMode="text"
                autoCapitalize="characters"
                autoComplete="off"
                spellCheck={false}
                maxLength={8}
                placeholder="e.g. KOODE0LL"
                value={code}
                onChange={e => setCode(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleVerify()}
                aria-label="Certificate code"
              />
            </div>
            <button type="button" className="cpl-btn cpl-btn-ink cpl-verify-btn" onClick={handleVerify}>
              <Stamp size={18} aria-hidden="true" />
              <span>Verify Certificate</span>
            </button>
          </div>

          <div className="cpl-samples">
            <span>Try sample code:</span>
            {SAMPLE_CODES.map(({ code, title }) => (
              <button key={code} type="button" className="cpl-sample-pill" onClick={() => setCode(code)}>
                {code} <span className="cpl-sample-title">{title}</span>
              </button>
            ))}
          </div>

          <p className="cpl-code-hash cpl-verify-note">
            <Lock size={14} aria-hidden="true" />
            Instant check against the public ledger. Completely free and open to everyone — no signup needed.
          </p>
        </div>
      </div>
    </section>
  )
}

const STEPS = [
  {
    num: '01',
    icon: Brush,
    title: 'The maker registers the piece',
    body: 'Maker uploads photos, materials, and creation notes. CraftProof generates an unforgeable QR certificate to stamp or hang on the physical piece.',
    foot: 'Studio Generation · QR Placard',
  },
  {
    num: '02',
    icon: ArrowLeftRight,
    title: 'Every handover is confirmed and recorded',
    body: 'When the work moves from studio to gallery, and gallery to collector, each party digitally confirms the handover in seconds.',
    foot: 'Mutual Approval · Two-Party Signoff',
  },
  {
    num: '03',
    icon: Globe,
    title: 'Anyone can check it, forever',
    body: 'Anyone holding or inspecting the item scans the code to view the complete story. Sealed into the public ledger so no one can quietly rewrite history.',
    foot: 'Open Access · Unalterable Ledger',
  },
]

function HowItWorks() {
  return (
    <section className="cpl-section">
      <div className="cpl-centered">
        <span className="cpl-eyebrow cpl-label-sm">Archival Architecture</span>
        <h2 className="cpl-headline-lg">How CraftProof Works</h2>
        <p className="cpl-body-lg">From clay and timber to an unalterable record.</p>
      </div>
      <div className="cpl-steps">
        {STEPS.map(s => (
          <div key={s.num} className="cpl-step">
            <div>
              <div className="cpl-step-top">
                <span className="cpl-step-num">{s.num}</span>
                <span className="cpl-step-icon"><s.icon size={20} aria-hidden="true" /></span>
              </div>
              <h3 className="cpl-headline-sm">{s.title}</h3>
              <p className="cpl-body-md">{s.body}</p>
            </div>
            <div className="cpl-step-foot"><span>{s.foot}</span></div>
          </div>
        ))}
      </div>
    </section>
  )
}

function TamperStory() {
  return (
    <section className="cpl-band cpl-band-subtle">
      <div className="cpl-band-inner">
        <div style={{ maxWidth: '48rem', marginBottom: 'var(--cpl-space-xl)' }}>
          <span className="cpl-eyebrow cpl-label-sm">Differentiator &amp; Security</span>
          <h2 className="cpl-headline-lg" style={{ marginBottom: 'var(--cpl-space-sm)' }}>
            What if someone attempts to fake the history?
          </h2>
          <p className="cpl-body-lg cpl-tamper-lede">
            Unlike ordinary paper certificates or static PDF receipts, any unauthorized
            edit immediately shatters the ledger continuity.
          </p>
        </div>

        <div className="cpl-compare">
          {/* State A — intact */}
          <div className="cpl-state-card">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--cpl-space-md)' }}>
              <div className="cpl-state-head">
                <span className="cpl-state-tag">Authentic Ledger State</span>
                <span className="cpl-badge cpl-badge-success">
                  <BadgeCheck size={16} aria-hidden="true" />
                  VERIFIED AUTHENTIC
                </span>
              </div>
              <div className="cpl-record-strip cpl-ok">
                <div className="cpl-record-top">
                  <span>CERTIFICATE RECORD</span>
                  <span style={{ color: 'var(--cpl-success)', fontWeight: 600 }}>STATE: INTACT</span>
                </div>
                <p className="cpl-record-title">Raku Vessel No. 14</p>
                <div className="cpl-record-lines cpl-code-hash">
                  <div>Studio Origin: Meera Krishnan <strong>[CONFIRMED]</strong></div>
                  <div>Gallery Ledger: Kalakriti Gallery <strong>[CONFIRMED]</strong></div>
                  <div>Current Holder: Jonathan Price <strong>[CONFIRMED]</strong></div>
                </div>
              </div>
              <p className="cpl-body-md cpl-state-body">
                Every confirmation aligns with the public checkpoints. The lineage is
                intact from the artist's studio.
              </p>
            </div>
            <div className="cpl-state-foot cpl-ok">
              <BadgeCheck size={18} aria-hidden="true" />
              <span>Sealed in the public ledger · Zero discrepancies</span>
            </div>
          </div>

          {/* State B — tampered */}
          <div className="cpl-state-card">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--cpl-space-md)' }}>
              <div className="cpl-state-head">
                <span className="cpl-state-tag">Altered Ledger State</span>
                <span className="cpl-badge cpl-badge-error">
                  <AlertTriangle size={16} aria-hidden="true" />
                  WARNING: ALTERED RECORD
                </span>
              </div>
              <div className="cpl-record-strip cpl-bad">
                <div className="cpl-record-top">
                  <span>TAMPER AUDIT</span>
                  <span style={{ fontWeight: 600 }}>STATUS: COMPROMISED</span>
                </div>
                <p className="cpl-record-title">Counterfeit Entry Flagged</p>
                <p className="cpl-body-sm cpl-tamper-detail">
                  Tampered step detected: transfer record #2 was modified offline.
                  Signature mismatch at step 2.
                </p>
              </div>
              <p className="cpl-body-md cpl-state-body">
                If someone creates a counterfeit tag or edits records, CraftProof catches
                the alteration instantly and warns the buyer in bold red. The record
                cannot be quietly forged.
              </p>
            </div>
            <div className="cpl-state-foot cpl-bad">
              <AlertTriangle size={18} aria-hidden="true" />
              <span>Tamper flag broadcast to public ledger</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

const AUDIENCES = [
  {
    icon: Hammer,
    kicker: 'Studio Artisans & Guilds',
    title: 'For Makers & Studios',
    tagline: 'Protect your name, legacy, and craft.',
    points: [
      { icon: BadgeCheck, text: <><strong>Permanent attribution:</strong> you are forever recorded as the original creator.</> },
      { icon: Printer, text: <><strong>Instant print-ready QR tags</strong> and certificate cards to ship with your work.</> },
      { icon: TrendingUp, text: <><strong>Strengthen resale value</strong> for your collectors without tedious paper certificates.</> },
    ],
    cta: { label: 'Join as a Maker', to: '/signup', kind: 'cpl-btn-ink' },
  },
  {
    icon: Building2,
    kicker: 'Curators & Institutions',
    title: 'For Galleries & Curators',
    tagline: 'Frictionless provenance management.',
    points: [
      { icon: ArrowLeftRight, text: <><strong>Accept inventory handovers</strong> with one tap — zero paperwork.</> },
      { icon: ListChecks, text: <><strong>Offer buyers definitive proof</strong> of authenticity at the point of sale.</> },
      { icon: ScrollText, text: <><strong>Track gallery exhibitions</strong> and provenance for every collected work.</> },
    ],
    cta: { label: 'Register Your Gallery', to: '/signup', kind: 'cpl-btn-soft' },
  },
]

function Audiences() {
  return (
    <section className="cpl-section" id="makers">
      <div className="cpl-centered">
        <span className="cpl-eyebrow cpl-label-sm">Tailored for the Craft Ecosystem</span>
        <h2 className="cpl-headline-lg">Built for Studios and Exhibition Spaces</h2>
        <p className="cpl-body-lg">Designed around the tactile workflows of physical object creation.</p>
      </div>
      <div className="cpl-audiences">
        {AUDIENCES.map(a => (
          <div key={a.title} className="cpl-audience">
            <div>
              <div className="cpl-audience-icon"><a.icon size={28} aria-hidden="true" /></div>
              <span className="cpl-audience-kicker">{a.kicker}</span>
              <h3 className="cpl-headline-md">{a.title}</h3>
              <p className="cpl-audience-tagline cpl-headline-sm">{a.tagline}</p>
              <ul>
                {a.points.map((p, i) => (
                  <li key={i}>
                    <p.icon size={20} aria-hidden="true" />
                    <span className="cpl-body-md">{p.text}</span>
                  </li>
                ))}
              </ul>
            </div>
            <Link to={a.cta.to} className={`cpl-btn ${a.cta.kind} cpl-btn-lg`}>
              <span>{a.cta.label}</span>
              <ArrowRight size={16} aria-hidden="true" />
            </Link>
          </div>
        ))}
      </div>
    </section>
  )
}

function TrustPlacard() {
  return (
    <section className="cpl-band cpl-band-tint">
      <div className="cpl-band-inner">
        <div className="cpl-trust-card">
          <Quote size={36} className="cpl-trust-quote-icon" aria-hidden="true" />
          <ShieldCheck size={180} className="cpl-trust-watermark" strokeWidth={1} aria-hidden="true" />
          <blockquote>
            “Every time a piece changes hands, the person handing it over digitally
            confirms it — a tamper-evident mark: any later attempt to alter that
            confirmation is detected and shown, never silently accepted. All
            confirmations are also sealed into a public ledger, so even
            CraftProof can't quietly alter a piece's history without it being detectable.”
          </blockquote>
          <div className="cpl-trust-attrib"><span>The CraftProof Trust Mandate</span></div>
        </div>
      </div>
    </section>
  )
}

function Footer() {
  return (
    <footer className="cpl-footer">
      <div className="cpl-footer-inner">
        <div className="cpl-footer-grid">
          <div className="cpl-footer-brand">
            <div className="cpl-footer-brandmark">
              <span className="cpl-footer-brandname">CraftProof</span>
              <span className="cpl-footer-chip">Registry &amp; Provenance</span>
            </div>
            <p className="cpl-body-md cpl-footer-blurb">
              Archival ledger and provenance for physical studio works. Uncompromising
              authenticity for ceramics, woodworking, and fine metalsmithing.
            </p>
            <p className="cpl-footer-tag">Authenticity you can hold.</p>
          </div>
          <div className="cpl-footer-col">
            <span className="cpl-footer-col-title">Atelier Ledger</span>
            <Link to="/how-it-works">How it Works</Link>
            <Link to="/ledger">Public Ledger</Link>
            <Link to="/developers">Public API</Link>
            <a href="#verify">Verify a Piece</a>
            <a href="#makers">Makers &amp; Galleries</a>
          </div>
          <div className="cpl-footer-col">
            <span className="cpl-footer-col-title">Studio Access</span>
            <Link to="/signup">Sign up</Link>
            <Link to="/login">Log in</Link>
            <Link to="/how-it-works">Archival Spec</Link>
          </div>
        </div>
        <div className="cpl-footer-meta">
          <p>CraftProof Colophon © 2026. Built on open standards under the MIT License.</p>
          <p className="cpl-footer-meta-right">Tamper-Evident Physical Registry</p>
        </div>
      </div>
    </footer>
  )
}

export default function Landing() {
  return (
    <div className="cpl">
      <Header />
      <main style={{ paddingTop: 64, background: 'var(--cpl-paper)' }}>
        <Hero />
        <VerifyCard />
        <HowItWorks />
        <TamperStory />
        <Audiences />
        <TrustPlacard />
      </main>
      <Footer />
    </div>
  )
}
