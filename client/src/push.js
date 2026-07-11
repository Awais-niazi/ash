// Web Push subscription flow (client side).
// Requires a secure context (HTTPS or localhost) — service workers won't
// register over plain HTTP, so on the phone the app must be served over HTTPS.

const BASE_URL = import.meta.env.VITE_API_URL;

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) output[i] = raw.charCodeAt(i);
  return output;
}

export function pushSupported() {
  return (
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

function authHeaders() {
  const token = localStorage.getItem("access_token");
  return { Authorization: `Bearer ${token}` };
}

// Register the SW, ask permission, subscribe, and store the subscription
// server-side. Throws a descriptive Error on any failure.
export async function enablePush() {
  if (!pushSupported()) {
    throw new Error("Notifications aren't supported on this device/browser.");
  }
  if (!window.isSecureContext) {
    throw new Error(
      "Notifications need a secure (https://) connection — open Ash over HTTPS."
    );
  }

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("Notification permission was denied.");
  }

  const reg = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;

  const keyRes = await fetch(`${BASE_URL}/api/push/key/`, {
    headers: authHeaders(),
  });
  const { publicKey } = await keyRes.json();
  if (!publicKey) {
    throw new Error("Server has no VAPID key configured yet.");
  }

  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey),
    });
  }

  const res = await fetch(`${BASE_URL}/api/push/subscribe/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ subscription: sub.toJSON() }),
  });
  if (!res.ok) throw new Error("Failed to save the subscription on the server.");
  return true;
}

// Fire a test notification to confirm the whole pipeline works.
export async function sendTestPush() {
  const res = await fetch(`${BASE_URL}/api/push/test/`, {
    method: "POST",
    headers: authHeaders(),
  });
  return res.ok;
}
