/**
 * SCAccountCard — Enhanced SoundCloud account card for the dashboard.
 * Shows profile data from Playwright login: avatar, stats, session status.
 */

import React, { useState } from "react";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

function formatCount(n) {
  if (!n) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export default function SCAccountCard({ account, onRefresh }) {
  const [checking, setChecking] = useState(false);
  const [relogging, setRelogging] = useState(false);
  const [status, setStatus] = useState(null);

  const handleHealthCheck = async () => {
    setChecking(true);
    setStatus(null);
    try {
      const res = await axios.post(`${API_BASE}/api/v1/soundcloud/validate`, {
        account_id: account.id,
      });
      if (res.data.valid) {
        setStatus({ type: "success", msg: "Session is active" });
        onRefresh?.();
      } else if (res.data.needs_relogin) {
        setStatus({ type: "warning", msg: "Session expired — re-login needed" });
      } else {
        setStatus({ type: "error", msg: res.data.error || "Unknown error" });
      }
    } catch (err) {
      setStatus({ type: "error", msg: err.response?.data?.detail || err.message });
    } finally {
      setChecking(false);
    }
  };

  const handleRelogin = async () => {
    setRelogging(true);
    setStatus(null);
    try {
      const res = await axios.post(`${API_BASE}/api/v1/soundcloud/relogin`, {
        account_id: account.id,
      });
      if (res.data.success) {
        setStatus({ type: "success", msg: "Re-logged in successfully!" });
        onRefresh?.();
      } else {
        setStatus({ type: "error", msg: res.data.message || "Re-login failed" });
      }
    } catch (err) {
      setStatus({ type: "error", msg: err.response?.data?.detail || err.message });
    } finally {
      setRelogging(false);
    }
  };

  const needsReauth = account.status === "needs_reauth";

  return (
    <div className={`sc-account-card ${needsReauth ? "needs-reauth" : ""}`}>
      <div className="card-header">
        <div className="avatar-section">
          {account.avatar_url ? (
            <img src={account.avatar_url} alt={account.username} className="avatar" />
          ) : (
            <div className="avatar placeholder">
              {(account.username || "?")[0].toUpperCase()}
            </div>
          )}
          <div className="user-info">
            <div className="display-name">
              {account.display_name || account.username}
              {account.is_verified && <span className="verified-badge">&#10003;</span>}
            </div>
            <div className="username">@{account.username}</div>
          </div>
        </div>
        <div className={`status-badge ${needsReauth ? "warning" : "active"}`}>
          {needsReauth ? "Needs Re-auth" : "Active"}
        </div>
      </div>

      <div className="stats-row">
        <div className="stat">
          <span className="stat-value">{formatCount(account.follower_count)}</span>
          <span className="stat-label">Followers</span>
        </div>
        <div className="stat">
          <span className="stat-value">{formatCount(account.following_count)}</span>
          <span className="stat-label">Following</span>
        </div>
        <div className="stat">
          <span className="stat-value">{formatCount(account.track_count)}</span>
          <span className="stat-label">Tracks</span>
        </div>
      </div>

      {account.bio && <p className="bio">{account.bio}</p>}

      <div className="auth-info">
        <span className="auth-badge">
          {account.auth_method === "browser_session" ? "Browser Session" : account.auth_method}
        </span>
      </div>

      {status && <div className={`card-status ${status.type}`}>{status.msg}</div>}

      <div className="card-actions">
        <button className="action-btn" onClick={handleHealthCheck} disabled={checking || relogging}>
          {checking ? "Checking..." : "Health Check"}
        </button>
        {needsReauth && (
          <button className="action-btn relogin" onClick={handleRelogin} disabled={checking || relogging}>
            {relogging ? "Logging in..." : "Re-Login"}
          </button>
        )}
        {account.profile_url && (
          <a href={account.profile_url} target="_blank" rel="noopener noreferrer" className="action-btn profile-link">
            View Profile
          </a>
        )}
      </div>

      <style>{`
        .sc-account-card { background: white; border: 1px solid #e0e0e0; border-radius: 12px; padding: 20px; transition: box-shadow 0.2s; }
        .sc-account-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        .sc-account-card.needs-reauth { border-color: #ffb74d; }
        .card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
        .avatar-section { display: flex; gap: 12px; align-items: center; }
        .avatar { width: 48px; height: 48px; border-radius: 50%; object-fit: cover; }
        .avatar.placeholder { display: flex; align-items: center; justify-content: center; background: #ff5500; color: white; font-size: 20px; font-weight: 700; }
        .user-info { display: flex; flex-direction: column; gap: 2px; }
        .display-name { font-size: 16px; font-weight: 700; color: #1a1a1a; display: flex; align-items: center; gap: 6px; }
        .verified-badge { display: inline-flex; align-items: center; justify-content: center; background: #ff5500; color: white; border-radius: 50%; width: 18px; height: 18px; font-size: 11px; }
        .username { font-size: 13px; color: #888; }
        .status-badge { padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }
        .status-badge.active { background: #e8f5e9; color: #2e7d32; }
        .status-badge.warning { background: #fff3e0; color: #e65100; }
        .stats-row { display: flex; gap: 24px; margin-bottom: 12px; padding: 12px 0; border-top: 1px solid #f0f0f0; border-bottom: 1px solid #f0f0f0; }
        .stat { display: flex; flex-direction: column; align-items: center; gap: 2px; }
        .stat-value { font-size: 18px; font-weight: 700; color: #1a1a1a; }
        .stat-label { font-size: 11px; color: #999; text-transform: uppercase; letter-spacing: 0.5px; }
        .bio { font-size: 13px; color: #555; line-height: 1.4; margin: 8px 0; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
        .auth-info { display: flex; gap: 8px; margin: 8px 0; }
        .auth-badge { padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; background: #f0f0f0; color: #666; }
        .card-status { padding: 8px 12px; border-radius: 6px; font-size: 12px; margin: 8px 0; }
        .card-status.success { background: #e8f5e9; color: #2e7d32; }
        .card-status.warning { background: #fff3e0; color: #e65100; }
        .card-status.error { background: #fdecea; color: #c62828; }
        .card-actions { display: flex; gap: 8px; margin-top: 12px; }
        .action-btn { padding: 7px 14px; border: 1px solid #ddd; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; background: white; color: #333; text-decoration: none; transition: all 0.2s; }
        .action-btn:hover:not(:disabled) { background: #f5f5f5; }
        .action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .action-btn.relogin { background: #ff5500; color: white; border-color: #ff5500; }
        .action-btn.relogin:hover:not(:disabled) { background: #e64d00; }
        .action-btn.profile-link { margin-left: auto; color: #ff5500; border-color: #ff5500; }
      `}</style>
    </div>
  );
}
