import { useState, useEffect, useRef } from "react";
import { login, sendMessage, resetChat } from "./api";
import "./App.css";

const BASE_URL = import.meta.env.VITE_API_URL;

async function speak(text) {
  try {
    const token = localStorage.getItem("access_token");
    const response = await fetch(`${import.meta.env.VITE_API_URL}/api/speak/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify({ text })
    });

    if (!response.ok) throw new Error("Speech failed");

    const audioBlob = await response.blob();
    const audioUrl = URL.createObjectURL(audioBlob);
    const audio = new Audio(audioUrl);
    audio.play();

    // Store reference to stop it later
    window.currentAudio = audio;
  } catch (err) {
    console.error("Speech error:", err);
  }
}

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loggedIn, setLoggedIn] = useState(
    !!localStorage.getItem("access_token")
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [briefingLoading, setBriefingLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Fetch morning briefing on login
  useEffect(() => {
    if (loggedIn && messages.length === 0) {
      fetchBriefing();
    }
  }, [loggedIn]);

  const fetchBriefing = async () => {
    setBriefingLoading(true);
    try {
      const token = localStorage.getItem("access_token");
      const response = await fetch(`${BASE_URL}/api/briefing/`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      const data = await response.json();
      if (data.briefing) {
        setMessages([{ role: "ash", text: data.briefing, isBriefing: true }]);
        speak(data.briefing);
      }
    } catch (err) {
      console.error("Briefing error:", err);
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

  const handleSend = async () => {
    if (!input.trim()) return;
    const userMessage = input;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: userMessage }]);
    setLoading(true);
    try {
      const data = await sendMessage(userMessage);
      setMessages((prev) => [...prev, { role: "ash", text: data.reply }]);
      speak(data.reply);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "ash", text: "Something went wrong. Try again." },
      ]);
    }
    setLoading(false);
  };

  const handleReset = async () => {
    window.speechSynthesis.cancel();
    await resetChat();
    setMessages([]);
    fetchBriefing();
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const stopSpeaking = () => {
  window.speechSynthesis.cancel();
  if (window.currentAudio) {
    window.currentAudio.pause();
    window.currentAudio.currentTime = 0;
  }
};

  if (!loggedIn) {
    return (
      <div className="login-container">
        <div className="login-box">
          <img src="/Ash.jpeg" alt="Ash" className="ash-avatar-login" />
          <h1>Ash</h1>
          <p>Your AI Personal Operating System</p>
          <form onSubmit={handleLogin}>
            <input
              type="text"
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {error && <p className="error">{error}</p>}
            <button type="submit">Login</button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-container">
      <div className="chat-header">
        <div className="ash-header-info">
          <img src="/Ash.jpeg" alt="Ash" className="ash-avatar-header" />
          <h2>Ash</h2>
        </div>
        <div className="header-actions">
          <button onClick={stopSpeaking} className="stop-btn">⏹ Stop</button>
          <button onClick={handleReset} className="reset-btn">New Chat</button>
        </div>
      </div>

      <div className="chat-messages">
        {briefingLoading && (
          <div className="briefing-loading">
            <div className="pulse" />
            <span>Ash is preparing your morning briefing...</span>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role} ${msg.isBriefing ? "briefing" : ""}`}>
            <span className="label">{msg.role === "user" ? "You" : "Ash"}</span>
            <pre>{msg.text}</pre>
          </div>
        ))}
        {loading && (
          <div className="message ash">
            <span className="label">Ash</span>
            <pre>Thinking...</pre>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Tell Ash what to do... (Enter to send)"
          rows={3}
        />
        <button onClick={handleSend} disabled={loading}>
          Send
        </button>
      </div>
    </div>
  );
}