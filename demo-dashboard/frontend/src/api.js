export async function getStatic(name) {
  const res = await fetch(`/static/${name}`);
  if (!res.ok) throw new Error(`static/${name} -> ${res.status}`);
  return res.json();
}

export async function getDemoAlerts() {
  const res = await fetch("/live/demo-alerts");
  if (!res.ok) throw new Error(`demo-alerts -> ${res.status}`);
  return res.json();
}

export async function liveTriage(model, uid) {
  const res = await fetch(
    `/live/triage?model=${encodeURIComponent(model)}&uid=${encodeURIComponent(uid)}`,
    { method: "POST" }
  );
  if (!res.ok) throw new Error(`live/triage -> ${res.status}`);
  return res.json();
}
