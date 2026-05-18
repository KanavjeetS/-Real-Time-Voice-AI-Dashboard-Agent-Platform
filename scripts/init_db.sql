-- ─────────────────────────────────────────────
--  AI Calling Agent — Database Schema
--  Runs automatically on first postgres startup
-- ─────────────────────────────────────────────

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Agents ────────────────────────────────────
CREATE TABLE IF NOT EXISTS agents (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(100) NOT NULL,
    description TEXT,
    system_prompt TEXT NOT NULL,
    voice_english VARCHAR(50) DEFAULT 'af_sarah',
    voice_hindi   VARCHAR(50) DEFAULT 'af_sky',
    language_mode VARCHAR(20) DEFAULT 'auto',  -- auto | en | hi
    is_active   BOOLEAN DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── Leads / CRM ───────────────────────────────
CREATE TABLE IF NOT EXISTS leads (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    phone        VARCHAR(20) NOT NULL,
    name         VARCHAR(100),
    email        VARCHAR(200),
    loan_amount  NUMERIC(15,2),
    loan_type    VARCHAR(50),
    status       VARCHAR(30) DEFAULT 'pending',  -- pending | contacted | interested | callback | converted | dnc
    notes        TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);

-- ── Calls ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS calls (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    call_sid         VARCHAR(50) UNIQUE,           -- Twilio Call SID
    agent_id         UUID REFERENCES agents(id),
    lead_id          UUID REFERENCES leads(id),
    phone_number     VARCHAR(20) NOT NULL,
    direction        VARCHAR(10) DEFAULT 'outbound', -- inbound | outbound
    status           VARCHAR(30) DEFAULT 'initiated', -- initiated | ringing | in-progress | completed | failed | no-answer
    duration_seconds INTEGER DEFAULT 0,
    detected_language VARCHAR(10) DEFAULT 'en',
    intent_label     VARCHAR(50),                  -- interested | confused | angry | spam | high_ticket | callback
    sentiment_score  NUMERIC(4,3),                 -- -1.0 to 1.0
    summary          TEXT,
    recording_url    TEXT,
    slack_alert_sent BOOLEAN DEFAULT false,
    started_at       TIMESTAMPTZ,
    ended_at         TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_calls_call_sid ON calls(call_sid);
CREATE INDEX IF NOT EXISTS idx_calls_status ON calls(status);
CREATE INDEX IF NOT EXISTS idx_calls_created_at ON calls(created_at DESC);

-- ── Call Turns (per-utterance transcripts) ────
CREATE TABLE IF NOT EXISTS call_turns (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    call_id         UUID NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
    turn_index      INTEGER NOT NULL,
    speaker         VARCHAR(10) NOT NULL,  -- user | agent
    transcript      TEXT NOT NULL,
    language        VARCHAR(10),
    intent          VARCHAR(50),
    sentiment       NUMERIC(4,3),
    latency_ms      INTEGER,               -- STT+LLM+TTS latency for this turn
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_turns_call_id ON call_turns(call_id);

-- ── Knowledge Base (RAG embeddings) ──────────
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content     TEXT NOT NULL,
    embedding   vector(768),
    source      VARCHAR(200),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kb_embedding
    ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ── Seed default agent ────────────────────────
INSERT INTO agents (name, description, system_prompt, voice_english, voice_hindi)
VALUES (
    'AI Calling Agent',
    'AI agent for loan follow-up and customer support calls',
    'You are a professional loan follow-up specialist for a financial services company. Your name is Priya. You speak naturally, warmly, and are fluent in both English and Hindi.

Your goals:
1. Greet the customer by name if available
2. Ask about their interest in the loan product
3. Handle objections with empathy
4. Capture key intent signals (interested, needs callback, confused, etc.)
5. Always be respectful — if customer says "not interested" after 2 attempts, thank them and end gracefully

Conversation flows:
- GREETING: "Hello, am I speaking with [Name]? This is Priya calling from [Company] regarding your loan enquiry."
- ELIGIBILITY: Explain loan amount, tenure, and EMI clearly
- EMI_QUERY: Provide calculation and flexible tenure options
- OBJECTION: Empathize and offer to call back at a better time
- CALLBACK_BOOKING: Confirm name, preferred time, and note it
- CLOSING: Always thank the customer regardless of outcome

Language rules:
- Detect the language the customer is speaking in
- Respond in the SAME language (Hindi or English)
- For Hinglish (mixed), match their style
- Never force language change on the customer

NEVER mention competitors. NEVER make false promises about approval.',
    'af_sarah',
    'af_sky'
) ON CONFLICT DO NOTHING;
