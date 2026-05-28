import { useState } from "react";
import { login, sendMessage, resetChat } from "./api";
import "./App.css";

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
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "ash", text: "Something went wrong. Try again." },
      ]);
    }
    setLoading(false);
  };

  const handleReset = async () => {
    await resetChat();
    setMessages([]);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!loggedIn) {
    return (
      <div className="login-container">
        <div className="login-box">
          <h1>🤖 Ash</h1>
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
        <h2>🤖 Ash</h2>
        <button onClick={handleReset} className="reset-btn">
          New Chat
        </button>
      </div>
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="empty-state">
            <h3>What can I do for you?</h3>
            <p>Ask me to write code, manage files, or handle your Git operations.</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
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