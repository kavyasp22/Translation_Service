export const MODEL_NAME_MAP = {
  gemma: "Model-A",
  indictrans2: "Model-B",
  googletrans: "Model-C",
};

export function getAnonymizedModelName(name) {
  if (!name) return "—";
  const lower = name.toLowerCase().trim();
  return MODEL_NAME_MAP[lower] || name;
}

export function anonymizeRouteReason(reason) {
  if (!reason) return "—";
  let str = reason;
  Object.entries(MODEL_NAME_MAP).forEach(([real, anon]) => {
    str = str.replace(new RegExp(real, "gi"), anon);
  });
  return str;
}
