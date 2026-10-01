import { useState, useEffect, useCallback } from "react";
import RoutingChain from "./components/RoutingChain.jsx";
import { countTokensAndStats } from "./utils/tokenCounter.js";
import { getAnonymizedModelName } from "./utils/modelAnonymizer.js";
import "./App.css";

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  (typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:8048`
    : "http://localhost:8048");

const ALL_LANGUAGES_LIST = [
  ["en", "English"],
  ["hi", "Hindi"], ["bn", "Bengali"], ["te", "Telugu"], ["mr", "Marathi"],
  ["ta", "Tamil"], ["ur", "Urdu"], ["gu", "Gujarati"], ["kn", "Kannada"],
  ["ml", "Malayalam"], ["or", "Odia"], ["pa", "Punjabi"], ["as", "Assamese"],
  ["ne", "Nepali"], ["mni", "Manipuri"], ["sa", "Sanskrit"], ["sd", "Sindhi"],
  ["kok", "Konkani"], ["doi", "Dogri"], ["mai", "Maithili"], ["sat", "Santali"],
  ["ks", "Kashmiri"], ["brx", "Bodo"], ["lus", "Mizo"],
  ["zh", "Chinese"], ["ar", "Arabic"], ["ps", "Pashto"], ["bal", "Balochi"], ["dv", "Divehi"],
  ["es", "Spanish"], ["fr", "French"], ["de", "German"], ["pt", "Portuguese"],
  ["ru", "Russian"], ["ja", "Japanese"], ["ko", "Korean"], ["it", "Italian"],
  ["tr", "Turkish"], ["vi", "Vietnamese"], ["id", "Indonesian"], ["ms", "Malay"],
  ["th", "Thai"], ["my", "Burmese"], ["km", "Khmer"], ["si", "Sinhala"],
  ["tl", "Filipino"], ["fa", "Persian"], ["nl", "Dutch"], ["pl", "Polish"],
  ["uk", "Ukrainian"], ["el", "Greek"], ["he", "Hebrew"], ["ro", "Romanian"],
  ["hu", "Hungarian"], ["cs", "Czech"], ["sv", "Swedish"], ["fi", "Finnish"],
  ["da", "Danish"], ["no", "Norwegian"], ["sw", "Swahili"],
].sort((a, b) => a[1].localeCompare(b[1]));

const LANGUAGES = [
  ["auto", "Auto-detect"],
  ...ALL_LANGUAGES_LIST,
];

const TARGET_LANGUAGES = [["en", "English"]];

export default function App() {
  const [text, setText] = useState("");
  const [sourceLang, setSourceLang] = useState("auto");
  const [targetLang, setTargetLang] = useState("en");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [health, setHealth] = useState(null);

  const inputStats = countTokensAndStats(text);
  const outputStats = countTokensAndStats(result?.translated_text || "");

  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      const data = await res.json();
      setHealth(data);
    } catch {
      setHealth({ status: "unreachable", models: {} });
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 15000);
    return () => clearInterval(interval);
  }, [checkHealth]);

  async function handleTranslate(e) {
    e.preventDefault();
    if (!text.trim()) return;

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/translate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, source_lang: sourceLang, target_lang: targetLang }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || `Request failed (${res.status})`);
      }
      setResult(data);
      setHistory((prev) => [{ input: text, ...data }, ...prev].slice(0, 20));
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app">
      <header className="app__header">
        <div>
          <h1 className="app__title">Translation Service</h1>
        </div>
        <HealthBadge health={health} />
      </header>

      <main className="app__main">
        <div className="main-content">
          <form className="panel" onSubmit={handleTranslate}>
            <div className="field-row">
              <div className="field">
                <label>Source language</label>
                <select value={sourceLang} onChange={(e) => setSourceLang(e.target.value)}>
                  {LANGUAGES.map(([code, name]) => (
                    <option key={code} value={code}>{name}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>Target language</label>
                <select value={targetLang} onChange={(e) => setTargetLang(e.target.value)}>
                  {TARGET_LANGUAGES.map(([code, name]) => (
                    <option key={code} value={code}>{name}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="field">
              <div className="label-with-stats">
                <label>Text to translate</label>
                {text.trim() && (
                  <div className="token-counter-badge input-token-badge">
                    <span>Tokens: ~{inputStats.tokens}</span>
                    <span className="dot">•</span>
                    <span>Words: {inputStats.words}</span>
                    <span className="dot">•</span>
                    <span>Chars: {inputStats.chars}</span>
                  </div>
                )}
              </div>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Native script, romanized, or code-mixed text — e.g. 'aj PM Modi ne BRICS summit me participate kiya'"
                rows={7}
              />
            </div>

            <button className="btn" type="submit" disabled={loading || !text.trim()}>
              {loading ? "Translating…" : "Translate"}
            </button>

            {error && <div className="error-box">{error}</div>}

            {result && (
              <div className="result-section">
                <div className="label-with-stats">
                  <label className="result-label">Translation Output</label>
                  <div className="token-counter-badge output-token-badge">
                    <span>Tokens: ~{outputStats.tokens}</span>
                    <span className="dot">•</span>
                    <span>Words: {outputStats.words}</span>
                    <span className="dot">•</span>
                    <span>Chars: {outputStats.chars}</span>
                  </div>
                </div>
                <div className="result-box">{result.translated_text}</div>
                <RoutingChain result={result} />
              </div>
            )}
          </form>
        </div>

        <aside className="history-sidebar">
          <div className="history-header">
            <h2 className="history__title">History</h2>
            {history.length > 0 && (
              <span className="history-count">{history.length} items</span>
            )}
          </div>

          {history.length === 0 ? (
            <div className="history-empty">
              <span>Your translation history will appear here.</span>
            </div>
          ) : (
            <div className="history__list">
              {history.map((item, i) => (
                <div className="history__item" key={i}>
                  <div className="history__input">{item.input}</div>
                  <div className="history__output">{item.translated_text}</div>
                  <div className="history__tag">
                    {getAnonymizedModelName(item.model_used)} · {item.latency_ms}ms
                  </div>
                </div>
              ))}
            </div>
          )}
        </aside>
      </main>
    </div>
  );
}

function HealthBadge({ health }) {
  if (!health) return null;
  const ok = health.status === "ok";
  // Filter out qwen from frontend model display completely
  const activeModels = Object.entries(health.models || {}).filter(
    ([name]) => name.toLowerCase() !== "qwen"
  );

  return (
    <div className={`health-badge ${ok ? "health-badge--ok" : "health-badge--degraded"}`}>
      <span className="health-badge__dot" />
      <span>{health.status}</span>
      <div className="health-badge__models">
        {activeModels.map(([name, isUp]) => (
          <span key={name} className={isUp ? "model-up" : "model-down"}>
            {getAnonymizedModelName(name)}
          </span>
        ))}
      </div>
    </div>
  );
}
