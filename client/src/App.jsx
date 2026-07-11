import { useState, useEffect, useRef } from "react";
import { login, sendMessage, resetChat } from "./api";
import { enablePush, pushSupported } from "./push";
import ReactMarkdown from "react-markdown";
import "./App.css";

const BASE_URL = import.meta.env.VITE_API_URL;

async function speak(text) {
  try {
    const token = localStorage.getItem("access_token");
    const response = await fetch(`${BASE_URL}/api/speak/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ text }),
    });
    if (!response.ok) return;
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.play();
    window.currentAudio = audio;
  } catch (err) {
    console.error("Speech error:", err);
  }
}

const MODES = [
  { key: "chat", label: "Chat", icon: "ti-message-circle" },
  { key: "tasks", label: "Tasks", icon: "ti-checkbox" },
  { key: "work", label: "Work", icon: "ti-file-text" },
  { key: "trips", label: "Trips", icon: "ti-plane" },
];

const MODE_PROMPTS = {
  tasks: "Show me my pending tasks",
  work: "Show me my assignments",
  trips: "Show me my planned trips",
};

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loggedIn, setLoggedIn] = useState(!!localStorage.getItem("access_token"));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeMode, setActiveMode] = useState("chat");
  const [briefingLoading, setBriefingLoading] = useState(false);
  const [notifOn, setNotifOn] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
  if (loggedIn && messages.length === 0) {
    if (import.meta.env.VITE_ENABLE_BRIEFING !== 'false') {
      fetchBriefing();
    }
  }
  }, [loggedIn]);

  // If notifications were already granted, silently refresh the subscription
  // on login so it stays valid on the server.
  useEffect(() => {
    if (loggedIn && pushSupported() && Notification.permission === "granted") {
      enablePush().then(() => setNotifOn(true)).catch(() => {});
    }
  }, [loggedIn]);

  const handleEnableNotifications = async () => {
    try {
      await enablePush();
      setNotifOn(true);
    } catch (e) {
      alert(e.message || "Could not enable notifications.");
    }
  };

  const fetchBriefing = async () => {
    setBriefingLoading(true);
    try {
      const token = localStorage.getItem("access_token");
      const res = await fetch(`${BASE_URL}/api/briefing/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (data.briefing) {
        const now = new Date();
        const time = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        setMessages([{ role: "ash", text: data.briefing, isBriefing: true, time }]);
        speak(data.briefing);
      }
    } catch (err) {
      console.error(err);
    }
    setBriefingLoading(false);
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      await login(username, password);
      setLoggedIn(true);
      setError("");
    } catch {
      setError("Invalid credentials");
    }
  };

  const sendMsg = async (text) => {
    if (!text.trim()) return;
    const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    setMessages((prev) => [...prev, { role: "user", text, time: now }]);
    setInput("");
    setLoading(true);
    try {
      const data = await sendMessage(text);
      const replyTime = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      setMessages((prev) => [...prev, { role: "ash", text: data.reply, time: replyTime }]);
      speak(data.reply);
    } catch {
      setMessages((prev) => [...prev, { role: "ash", text: "Something went wrong. Try again.", time: "" }]);
    }
    setLoading(false);
  };

  const handleSend = () => sendMsg(input);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleModeSwitch = (mode) => {
    setActiveMode(mode);
    if (mode !== "chat" && MODE_PROMPTS[mode]) {
      sendMsg(MODE_PROMPTS[mode]);
    }
  };

  const handleReset = async () => {
    window.speechSynthesis?.cancel();
    window.currentAudio?.pause();
    await resetChat();
    setMessages([]);
    setActiveMode("chat");
    fetchBriefing();
  };

  const stopSpeaking = () => {
    window.speechSynthesis?.cancel();
    if (window.currentAudio) {
      window.currentAudio.pause();
      window.currentAudio.currentTime = 0;
    }
  };

  if (!loggedIn) {
    return (
      <div className="login-screen">
        <div className="login-card">
          <div className="login-avatar-wrap">
            <img src="/Ash.jpeg" alt="Ash" className="login-avatar" />
            <div className="login-online-dot" />
          </div>
          <h1 className="login-title">Ash</h1>
          <p className="login-sub">Your AI Personal Operating System</p>
          <form onSubmit={handleLogin} className="login-form">
            <input
              type="text"
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="login-input"
            />
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="login-input"
            />
            {error && <p className="login-error">{error}</p>}
            <button type="submit" className="login-btn">Login</button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <div className="header">
        <div className="header-left">
          <div className="avatar-wrap">
            <img src="/Ash.jpeg" alt="Ash" className="avatar" />
            <div className="online-dot" />
          </div>
          <div className="header-info">
            <h2 className="header-name">Ash</h2>
            <span className="header-status">Online</span>
          </div>
        </div>
        <div className="header-right">
          {pushSupported() && (
            <button
              onClick={handleEnableNotifications}
              className="icon-btn"
              title={notifOn ? "Notifications on" : "Enable notifications"}
            >
              <i className={`ti ${notifOn ? "ti-bell" : "ti-bell-plus"}`} aria-hidden="true" />
            </button>
          )}
          <button onClick={stopSpeaking} className="icon-btn" title="Stop speaking">
            <i className="ti ti-player-stop" aria-hidden="true" />
          </button>
          <button onClick={handleReset} className="icon-btn" title="New chat">
            <i className="ti ti-edit" aria-hidden="true" />
          </button>
        </div>
      </div>

      <div className="mode-bar">
        {MODES.map((m) => (
          <button
            key={m.key}
            className={`mode-btn ${activeMode === m.key ? "active" : ""}`}
            onClick={() => handleModeSwitch(m.key)}
          >
            <i className={`ti ${m.icon}`} aria-hidden="true" />
            {m.label}
          </button>
        ))}
      </div>

      <div className="messages">
        {briefingLoading && (
          <div className="briefing-loading">
            <div className="pulse-dot" />
            <span>Preparing your morning briefing...</span>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`msg ${msg.role}`}>
            {msg.isBriefing && (
              <div className="briefing-badge">
                <i className="ti ti-sun" aria-hidden="true" /> Morning briefing
              </div>
            )}
            <div className="msg-label">{msg.role === "user" ? "You" : "Ash"}</div>
            <div className="msg-bubble">
              <ReactMarkdown>{msg.text}</ReactMarkdown>
            </div>
            {msg.time && <div className="msg-time">{msg.time}</div>}
          </div>
        ))}
        {loading && (
          <div className="msg ash">
            <div className="msg-label">Ash</div>
            <div className="msg-bubble typing-bubble">
              <div className="dot" />
              <div className="dot" />
              <div className="dot" />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-area">
        <div className="input-wrap">
          <textarea
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
            }}
            onKeyDown={handleKeyDown}
            placeholder="Tell Ash what to do..."
            rows={1}
            className="input-field"
          />
          <i className="ti ti-microphone input-mic" aria-hidden="true" />
        </div>
        <button onClick={handleSend} disabled={loading} className="send-btn">
          <i className="ti ti-arrow-up" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}