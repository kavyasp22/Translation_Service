import { getAnonymizedModelName, anonymizeRouteReason } from "../utils/modelAnonymizer.js";
import "./RoutingChain.css";

/**
 * Shows the fallback chain the request travelled through: which model was
 * tried, which one actually served the response, and how the route was
 * decided.
 */
export default function RoutingChain({ result }) {
  if (!result) return null;

  const { model_used, route_reason, script_type, detected_language, latency_ms, cache_hit, entity_issues } = result;

  const isLanguageSpecific = route_reason?.startsWith("language_specific_route");
  const isFallback = route_reason?.startsWith("fallback_from");
  const hasEntityIssues = Array.isArray(entity_issues) && entity_issues.length > 0;

  const anonModel = getAnonymizedModelName(model_used);
  const rawRoute = isLanguageSpecific ? `${route_reason.split(":")[1]} table` : route_reason;
  const anonRoute = anonymizeRouteReason(rawRoute);

  return (
    <div className="routing-chain">
      <div className="routing-chain__row">
        <span className="routing-chain__label">served by</span>
        <span className="routing-chain__model">{anonModel}</span>
        {isFallback && <span className="routing-chain__badge routing-chain__badge--warn">fallback triggered</span>}
        {cache_hit && <span className="routing-chain__badge routing-chain__badge--accent">cache hit</span>}
        {hasEntityIssues && <span className="routing-chain__badge routing-chain__badge--danger">entity auto-corrected</span>}
      </div>

      <div className="routing-chain__meta">
        <MetaItem label="detected language" value={detected_language || "—"} />
        <MetaItem label="script" value={script_type || "—"} />
        <MetaItem label="route" value={anonRoute} />
        <MetaItem label="latency" value={`${latency_ms} ms`} />
      </div>

      {hasEntityIssues && (
        <div className="routing-chain__entity-warning">
          <span className="routing-chain__entity-warning-title">
            ⚠ named-entity issue detected - an automatic correction was attempted, please double-check
          </span>
          <ul>
            {entity_issues.map((issue, i) => (
              <li key={i}>{issue}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function MetaItem({ label, value }) {
  return (
    <div className="routing-chain__meta-item">
      <span className="routing-chain__meta-label">{label}</span>
      <span className="routing-chain__meta-value">{value}</span>
    </div>
  );
}
