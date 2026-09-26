import { useEffect, useState } from "react";
import { Database, LoaderCircle, Send, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import type { LiveAnswer, LiveConnection } from "../lib/api";

export function LiveDatabaseAssistant() {
  const [connections, setConnections] = useState<LiveConnection[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [tables, setTables] = useState("");
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<Array<{ question: string; result: LiveAnswer }>>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.liveConnections().then((items) => {
      setConnections(items);
      setSelectedId(items[0]?.id ?? null);
    }).catch((caught) => setError(caught instanceof Error ? caught.message : "Could not load connections."));
  }, []);

  async function connect() {
    setBusy(true);
    setError("");
    try {
      const created = await api.createLiveConnection({
        name: name.trim(), database_url: url.trim(),
        allowed_tables: tables.split(",").map((item) => item.trim()).filter(Boolean),
      });
      setConnections((current) => [created, ...current]);
      setSelectedId(created.id);
      setUrl("");
      setName("");
      setTables("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save connection.");
    } finally { setBusy(false); }
  }

  async function disconnect() {
    if (selectedId === null) return;
    setBusy(true);
    setError("");
    try {
      await api.deleteLiveConnection(selectedId);
      const remaining = connections.filter((item) => item.id !== selectedId);
      setConnections(remaining);
      setSelectedId(remaining[0]?.id ?? null);
      setAnswers([]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not disconnect.");
    } finally { setBusy(false); }
  }

  async function ask() {
    if (selectedId === null || !question.trim()) return;
    setBusy(true);
    setError("");
    const prompt = question.trim();
    try {
      const result = await api.askLive(selectedId, prompt);
      setAnswers((current) => [...current, { question: prompt, result }]);
      setQuestion("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The query failed.");
    } finally { setBusy(false); }
  }

  return <div className="assistant-page">
    <header><div className="assistant-orb"><Database size={22} /></div><p className="eyebrow">LIVE DATABASE ASSISTANT</p><h1>Ask the live database</h1><span>Each question checks the current schema and runs a governed, read-only query.</span></header>
    <div className="assistant-source">
      <label>Connection<select value={selectedId ?? ""} onChange={(event) => { setSelectedId(Number(event.target.value) || null); setAnswers([]); }}><option value="">Choose a connection</option>{connections.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      {selectedId !== null && <button type="button" className="secondary-button" onClick={() => void disconnect()} disabled={busy}><Trash2 size={14} /> Disconnect</button>}
    </div>
    <section className="builder-card database-connect-form">
      <h2>Save a read-only PostgreSQL connection</h2>
      <label><span>Connection name</span><input value={name} onChange={(event) => setName(event.target.value)} placeholder="TLC warehouse" /></label>
      <label><span>Connection URL</span><input type="password" autoComplete="off" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="postgresql+psycopg://reader:password@host/database" /></label>
      <label><span>Allowed tables</span><input value={tables} onChange={(event) => setTables(event.target.value)} placeholder="curated.tlc_daily, curated.tlc_pickup_zone" /></label>
      <button type="button" onClick={() => void connect()} disabled={busy || !name.trim() || !url.trim() || !tables.trim()}>{busy ? <LoaderCircle className="spin" size={15} /> : <Database size={15} />} Save connection</button>
      <small>Credentials are stored in AWS Secrets Manager. Use a role with SELECT access only.</small>
    </section>
    {error && <div className="data-message error">{error}</div>}
    <section className="assistant-thread">
      {answers.map((item, index) => <div className="assistant-exchange" key={index}><p className="assistant-question">{item.question}</p><article><Database size={16} /><div><strong>Answer from executed SQL</strong><p>{item.result.answer}</p><details><summary>SQL and evidence · {item.result.row_count} rows</summary><pre>{item.result.sql}</pre><pre>{JSON.stringify(item.result.rows, null, 2)}</pre></details></div></article></div>)}
    </section>
    <footer className="assistant-composer"><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about a live table…" disabled={selectedId === null || busy} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void ask(); } }} /><button onClick={() => void ask()} disabled={selectedId === null || !question.trim() || busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <Send size={17} />}</button></footer>
  </div>;
}
