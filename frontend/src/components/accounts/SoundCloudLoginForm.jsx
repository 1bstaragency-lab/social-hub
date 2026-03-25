/**
 * SoundCloudLoginForm — replaces the old OAuth token fields for SoundCloud.
 *
 * Since SoundCloud's developer portal is private, we authenticate via
 * Playwright browser automation on the backend. The user provides their
 * SoundCloud email + password, which are encrypted at rest.
 */

import React, { useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function SoundCloudLoginForm({ onSuccess, onError, onClose }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      onError?.("Email and password are required");
      return;
    }

    setLoading(true);
    setStatus("Logging into SoundCloud via browser...");

    try {
      const res = await axios.post(`${API_BASE}/api/v1/soundcloud/login`, {
        email,
        password,
      });

      if (res.data.success) {
        setStatus("Login successful!");
        onSuccess?.(res.data);
      } else {
        setStatus("Login failed");
        onError?.(res.data.message || "Login failed");
      }
    } catch (err) {
      const msg =
        err.response?.data?.detail ||
        err.response?.data?.error ||
        err.message ||
        "Login failed";
      setStatus(`Error: ${msg}`);
      onError?.(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleLogin} className="sc-login-form">
      <div className="form-header">
        <div className="platform-badge soundcloud">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
            <path d="M11.56 8.87V17h8.76c1.85-.13 3.32-1.61 3.32-3.45 0-1.87-1.52-3.39-3.39-3.39-.36 0-.72.06-1.05.17-.18-2.44-2.22-4.36-4.7-4.36-1.07 0-2.06.36-2.85.97l-.09.06v1.87zm-1.22-.61v8.74h.5V8.13c-.17.04-.34.08-.5.13zm-1.21.54v8.2h.5v-8.5c-.18.09-.34.19-.5.3zm-1.22 1.13v7.07h.5V9.63c-.18.12-.34.27-.5.43v-.13zm-1.21 1.66v5.41h.5v-5.91c-.2.16-.36.33-.5.5zm-1.22 1.12v4.29h.5v-4.79c-.17.15-.34.32-.5.5zm-1.22.79v3.5h.5v-4c-.17.15-.34.32-.5.5zm-1.21.93v2.57h.5v-3.07c-.17.15-.34.32-.5.5zm-1.22 1.16v1.41h.5v-1.91c-.17.15-.34.32-.5.5z" />
          </svg>
          SoundCloud
        </div>
      </div>

      <p className="form-hint">
        Enter your SoundCloud login credentials. Your email and password are
        encrypted at rest and used for secure browser-based authentication.
      </p>

      <div className="form-group">
        <label htmlFor="sc-email">Email</label>
        <input
          id="sc-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="your@email.com"
          required
          disabled={loading}
          autoComplete="email"
        />
      </div>

      <div className="form-group">
        <label htmlFor="sc-password">Password</label>
        <input
          id="sc-password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="SoundCloud password"
          required
          disabled={loading}
          autoComplete="current-password"
        />
      </div>

      {status && (
        <div
          className={`form-status ${
            status.includes("Error") || status.includes("failed")
              ? "error"
              : status.includes("successful")
              ? "success"
              : "info"
          }`}
        >
          {loading && <span className="spinner" />}
          {status}
        </div>
      )}

      <div className="form-actions">
        <button type="button" className="btn btn-secondary" onClick={onClose} disabled={loading}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? "Connecting..." : "Connect SoundCloud"}
        </button>
      </div>

      <style>{`
        .sc-login-form { display: flex; flex-direction: column; gap: 16px; }
        .form-header { display: flex; align-items: center; gap: 12px; }
        .platform-badge { display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; border-radius: 8px; font-weight: 600; font-size: 14px; }
        .platform-badge.soundcloud { background: #ff5500; color: white; }
        .form-hint { font-size: 13px; color: #666; margin: 0; line-height: 1.4; }
        .form-group { display: flex; flex-direction: column; gap: 6px; }
        .form-group label { font-size: 13px; font-weight: 600; color: #333; }
        .form-group input { padding: 10px 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; outline: none; transition: border-color 0.2s; }
        .form-group input:focus { border-color: #ff5500; box-shadow: 0 0 0 3px rgba(255,85,0,0.1); }
        .form-group input:disabled { background: #f5f5f5; cursor: not-allowed; }
        .form-status { padding: 10px 14px; border-radius: 8px; font-size: 13px; display: flex; align-items: center; gap: 8px; }
        .form-status.info { background: #e8f4fd; color: #1565c0; }
        .form-status.error { background: #fdecea; color: #c62828; }
        .form-status.success { background: #e8f5e9; color: #2e7d32; }
        .spinner { width: 14px; height: 14px; border: 2px solid currentColor; border-top-color: transparent; border-radius: 50%; animation: spin 0.6s linear infinite; flex-shrink: 0; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .form-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 8px; }
        .btn { padding: 10px 20px; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .btn-primary { background: #ff5500; color: white; }
        .btn-primary:hover:not(:disabled) { background: #e64d00; }
        .btn-secondary { background: #f0f0f0; color: #333; }
        .btn-secondary:hover:not(:disabled) { background: #e0e0e0; }
      `}</style>
    </form>
  );
}
