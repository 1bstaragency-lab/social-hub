import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { accountsApi } from "../../services/api";
import { X } from "lucide-react";
import toast from "react-hot-toast";

const PLATFORM_FIELDS = {
  soundcloud: [
    { key: "access_token", label: "OAuth Access Token", type: "password" },
    { key: "client_id", label: "Client ID", type: "text" },
  ],
  tiktok: [
    { key: "session_cookies", label: "Session Cookies (JSON)", type: "textarea" },
  ],
  twitter: [
    { key: "api_key", label: "API Key", type: "text" },
    { key: "api_secret", label: "API Secret", type: "password" },
    { key: "access_token", label: "Access Token", type: "password" },
    { key: "access_token_secret", label: "Access Token Secret", type: "password" },
    { key: "bearer_token", label: "Bearer Token", type: "password" },
  ],
  spotify: [
    { key: "client_id", label: "Client ID", type: "text" },
    { key: "client_secret", label: "Client Secret", type: "password" },
    { key: "access_token", label: "Access Token", type: "password" },
    { key: "refresh_token", label: "Refresh Token", type: "password" },
  ],
};

const AUTH_METHODS = {
  soundcloud: "api_token",
  tiktok: "browser_session",
  twitter: "api_token",
  spotify: "oauth2",
};

export default function AddAccountModal({ onClose, organizationId }) {
  const qc = useQueryClient();
  const [platform, setPlatform] = useState("soundcloud");
  const [username, setUsername] = useState("");
  const [proxy, setProxy] = useState({ server: "", username: "", password: "" });
  const [creds, setCreds] = useState({});

  const create = useMutation({
    mutationFn: (data) => accountsApi.create(data),
    onSuccess: () => {
      toast.success("Account added successfully");
      qc.invalidateQueries(["accounts"]);
      onClose();
    },
    onError: (err) => toast.error(err.response?.data?.detail || "Failed to add account"),
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    create.mutate({
      organization_id: organizationId || "00000000-0000-0000-0000-000000000001",
      platform,
      username,
      auth_method: AUTH_METHODS[platform],
      credentials: creds,
      proxy_config: proxy.server ? proxy : null,
    });
  };

  const fields = PLATFORM_FIELDS[platform] || [];

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-900">Add Social Account</h2>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-100 rounded-lg transition">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">Platform</label>
            <div className="grid grid-cols-4 gap-2">
              {["soundcloud", "tiktok", "twitter", "spotify"].map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => { setPlatform(p); setCreds({}); }}
                  className={`py-2 text-xs rounded-lg border capitalize transition ${
                    platform === p
                      ? "border-indigo-500 bg-indigo-50 text-indigo-700 font-semibold"
                      : "border-gray-200 hover:border-gray-300"
                  }`}
                >
                  {p === "twitter" ? "Twitter/X" : p}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Username</label>
            <input
              required
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={`@username on ${platform}`}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
          </div>

          {fields.map((f) => (
            <div key={f.key}>
              <label className="block text-xs font-medium text-gray-600 mb-1">{f.label}</label>
              {f.type === "textarea" ? (
                <textarea
                  rows={3}
                  value={creds[f.key] || ""}
                  onChange={(e) => setCreds({ ...creds, [f.key]: e.target.value })}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400 resize-none font-mono text-xs"
                />
              ) : (
                <input
                  type={f.type}
                  value={creds[f.key] || ""}
                  onChange={(e) => setCreds({ ...creds, [f.key]: e.target.value })}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400"
                />
              )}
            </div>
          ))}

          {/* Optional proxy */}
          <details className="group">
            <summary className="text-xs font-medium text-gray-500 cursor-pointer hover:text-gray-700 select-none">
              Proxy settings (optional)
            </summary>
            <div className="mt-2 space-y-2 pl-2 border-l-2 border-gray-100">
              <input
                type="text"
                placeholder="Server (e.g. http://proxy.example.com:8080)"
                value={proxy.server}
                onChange={(e) => setProxy({ ...proxy, server: e.target.value })}
                className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2"
              />
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="text"
                  placeholder="Username"
                  value={proxy.username}
                  onChange={(e) => setProxy({ ...proxy, username: e.target.value })}
                  className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2"
                />
                <input
                  type="password"
                  placeholder="Password"
                  value={proxy.password}
                  onChange={(e) => setProxy({ ...proxy, password: e.target.value })}
                  className="w-full text-xs border border-gray-200 rounded-lg px-3 py-2"
                />
              </div>
            </div>
          </details>

          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose} className="flex-1 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 transition">
              Cancel
            </button>
            <button type="submit" disabled={create.isPending} className="flex-1 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition disabled:opacity-60">
              {create.isPending ? "Adding…" : "Add Account"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
