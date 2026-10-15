// Small, presentation-only data reshaping helpers. None of these
// compute a statistic -- they only convert the shape the API already
// returns ([key, count] pairs or {key: count} dicts) into the
// [{name, count}] shape Recharts expects.

export function pairsToChartData(pairs) {
  return (pairs || []).map(([name, count]) => ({ name: String(name), count }));
}

export function dictToChartData(dict) {
  return Object.entries(dict || {}).map(([name, count]) => ({ name, count }));
}
