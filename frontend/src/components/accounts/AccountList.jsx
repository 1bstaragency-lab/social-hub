import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { accountsApi } from "../../services/api";
import {
  Plus,
  RefreshCw,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Trash2,
  Edit,
} from "lucide-react";
import toast from "react-hot-toast";
import AddAccountModal from "./AddAccountModal";
import EngagementPanel from "./EngagementPanel";
import SCAccountCard from "./SCAccountCard";

const STATUS_CONFIG = {
  active: {
    color: "text-green-600 bg-green-50",
    icon: CheckCircle,
    label: "Active",
  },
  paused: {
    color: "text-yellow-600 bg-yellow-50",
    icon: AlertTriangle,
    label: "Paused",
  },
  needs_reauth: {
    color: "text-red-600 bg-red-50",
    icon: XCircle,
    label: "Needs Re-auth",
  },
  suspended: {
    color: "text-gray-600 bg-gray-100",
    icon: XCircle,
    label: "Suspended",
  },
  disabled: {
    color: "text-gray-400 bg-gray-50",
    icon: XCircle,
    label: "Disabled",
  },
};

const PLATFORM_EMOJI = {
  soundcloud: "\u{1F3B5}",
  tiktok: "\u{1F3AC}",
  twitter: "\u{1F426}",
  spotify: "\u{1F3A7}",
};

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.disabled;
  const Icon = cfg.icon;
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.color}`}
    >
      <Icon size={11} />
      {cfg.label}
    </span>
  );
}

export default function AccountList() {
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [selectedAccount, setSelectedAccount] = useState(null);
  const [filterPlatform, setFilterPlatform] = useState("");
  const [filterStatus, setFilterStatus] = useState("");

  const { data: accounts = [], isLoading } = useQuery({
    queryKey: ["accounts", filterPlatform, filterStatus],
    queryFn: () =>
      accountsApi.list({
        ...(filterPlatform && { platform: filterPlatform }),
        ...(filterStatus && { status: filterStatus }),
        limit: 200,
      }),
    select: (r) => r.data,
  });

  const healthCheck = useMutation({
    mutationFn: (id) => accountsApi.healthCheck(id),
    onSuccess: () => {
      toast.success("Health check complete");
      qc.invalidateQueries(["accounts"]);
    },
  });

  const deleteAccount = useMutation({
    mutationFn: (id) => accountsApi.delete(id),
    onSuccess: () => {
      toast.success("Account removed");
      qc.invalidateQueries(["accounts"]);
    },
  });

  const healthCheckAll = () => {
    accountsApi.healthCheckAll();
    toast.success("Running health check on all accounts\u2026");
  };

  const refreshAccounts = () => qc.invalidateQueries(["accounts"]);

  return (
    <div className="space-y-4">
      {/* Header bar */}
      <div className="flex flex-wrap gap-3 items-center justify-between">
        <div className="flex gap-2">
          <select
            className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white"
            value={filterPlatform}
            onChange={(e) => setFilterPlatform(e.target.value)}
          >
            <option value="">All Platforms</option>
            <option value="soundcloud">SoundCloud</option>
            <option value="tiktok">TikTok</option>
            <option value="twitter">Twitter/X</option>
            <option value="spotify">Spotify</option>
          </select>
          <select
            className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 bg-white"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
          >
            <option value="">All Statuses</option>
            <option value="active">Active</option>
            <option value="needs_reauth">Needs Re-auth</option>
            <option value="paused">Paused</option>
          </select>
        </div>
        <div className="flex gap-2">
          <button
            onClick={healthCheckAll}
            className="flex items-center gap-1.5 text-sm px-3 py-1.5 border border-gray-200 rounded-lg hover:bg-gray-50 transition"
          >
            <RefreshCw size={14} /> Check All
          </button>
          <button
            onClick={() => setShowAdd(true)}
            className="flex items-center gap-1.5 text-sm px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition"
          >
            <Plus size={14} /> Add Account
          </button>
        </div>
      </div>

      {/* Account cards */}
      {isLoading ? (
        <p className="text-gray-400 text-sm text-center py-10">
          Loading accounts\u2026
        </p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {accounts.map((account) =>
            account.platform === "soundcloud" ? (
              <SCAccountCard
                key={account.id}
                account={account}
                onRefresh={refreshAccounts}
              />
            ) : (
              <div
                key={account.id}
                className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 hover:shadow-md transition-shadow"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">
                      {PLATFORM_EMOJI[account.platform]}
                    </span>
                    <div>
                      <p className="font-semibold text-gray-900 text-sm">
                        {account.username}
                      </p>
                      <p className="text-xs text-gray-400 capitalize">
                        {account.platform}
                      </p>
                    </div>
                  </div>
                  <StatusBadge status={account.status} />
                </div>

                <div className="grid grid-cols-3 gap-2 mb-3">
                  <div className="text-center">
                    <p className="text-xs text-gray-400">Followers</p>
                    <p className="font-semibold text-gray-800 text-sm">
                      {account.follower_count?.toLocaleString()}
                    </p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-gray-400">Following</p>
                    <p className="font-semibold text-gray-800 text-sm">
                      {account.following_count?.toLocaleString()}
                    </p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-gray-400">Verified</p>
                    <p className="font-semibold text-gray-800 text-sm">
                      {account.is_verified ? "\u2713" : "\u2014"}
                    </p>
                  </div>
                </div>

                {/* Engagement quick actions */}
                <div className="border-t border-gray-50 pt-3">
                  <p className="text-xs font-medium text-gray-500 mb-2">
                    Quick Actions
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {["like", "repost", "follow", "comment", "play"].map(
                      (action) => (
                        <button
                          key={action}
                          onClick={() =>
                            setSelectedAccount({
                              account,
                              defaultAction: action,
                            })
                          }
                          className="text-xs px-2 py-1 rounded-md bg-gray-100 hover:bg-indigo-100 hover:text-indigo-700 transition capitalize"
                        >
                          {action}
                        </button>
                      )
                    )}
                  </div>
                </div>

                <div className="flex gap-2 mt-3 border-t border-gray-50 pt-3">
                  <button
                    onClick={() => healthCheck.mutate(account.id)}
                    className="flex-1 text-xs flex items-center justify-center gap-1 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 transition"
                  >
                    <RefreshCw size={11} /> Health Check
                  </button>
                  <button
                    onClick={() => {
                      if (confirm(`Remove ${account.username}?`))
                        deleteAccount.mutate(account.id);
                    }}
                    className="p-1.5 rounded-lg border border-red-100 text-red-400 hover:bg-red-50 transition"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            )
          )}
          {accounts.length === 0 && (
            <div className="col-span-3 text-center py-16 text-gray-400">
              <p className="text-lg mb-2">No accounts yet</p>
              <p className="text-sm">
                Click "Add Account" to connect your first social account.
              </p>
            </div>
          )}
        </div>
      )}

      {showAdd && <AddAccountModal onClose={() => setShowAdd(false)} />}
      {selectedAccount && (
        <EngagementPanel
          account={selectedAccount.account}
          defaultAction={selectedAccount.defaultAction}
          onClose={() => setSelectedAccount(null)}
        />
      )}
    </div>
  );
}
