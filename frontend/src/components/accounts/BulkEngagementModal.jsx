/**
 * BulkEngagementModal — fire the same action across many accounts at once.
 * Each account gets a randomised delay to look organic.
 */

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { accountsApi, engagementApi } from "../../services/api";
import { X, Users, Zap } from "lucide-react";
import toast from "react-hot-toast";

const ACTIONS = [
  "like", "unlike", "repost", "unrepost",
  "comment", "follow", "unfollow", "play", "save", "add_to_playlist",
];

export default function BulkEngagementModal({ onClose }) {
  const [selectedIds, setSelectedIds] = useState([]);
  const [action, setAction] = useState("like");
  const [targetUrl, setTargetUrl] = useState("");
  const [targetId, setTargetId] = useState("");
  const [commentText, setCommentText] = useState("");
  const [delayMin, setDelayMin] = useState(5);
  const [delayMax, setDelayMax] = useState(30);
  const [scheduleAt, setScheduleAt] = useState("");
  const [filterPlatform, setFilterPlatform] = useState("");

  const { data: accounts = [] } = useQuery({
    queryKey: ["accounts-all"],
    queryFn: () => accountsApi.list({ limit: 200, status: "active" }),
    select: (r) => r.data,
  });

  const filtered = filterPlatform
    ? accounts.filter((a) => a.platform === filterPlatform)
    : accounts;

  const toggleAll = () => {
    if (selectedIds.length === filtered.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(filtered.map((a) => a.id));
    }
  };

  const toggle = (id) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const bulk = useMutation({
    mutationFn: (data) => engagementApi.bulk(data),
    onSuccess: (r) => {
      toast.success(`Bulk ${action} dispatched across ${selectedIds.length} accounts`);
      onClose();
    },
    onError: (err) => toast.error(err.response?.data?.detail || "Bulk action failed"),
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!selectedIds.length) return toast.error("Select at least one account");
    bulk.mutate({
      account_ids: selectedIds,
      action_type: action,
      target_url: targetUrl || undefined,
      target_platform_id: targetId || undefined,
      comment_text: commentText || undefined,
      delay_min_seconds: delayMin,
      delay_max_seconds: delayMax,
      scheduled_at: scheduleAt ? new Date(scheduleAt).toISOString() : undefined,
    });
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Users size={16} className="text-indigo-600" />
            <h2 className="font-semibold text-gray-900">Bulk Engagement</h2>
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-100 rounded-lg transition">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col flex-1 overflow-hidden">
          <div className="overflow-y-auto p-5 space-y-4 flex-1">
            {/* Action */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">Action Type</label>
              <select
                value={action}
                onChange={(e) => setAction(e.target.value)}
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2"
              >
                {ACTIONS.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </div>

            {/* Target */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Target URL</label>
                <input
                  type="text"
                  value={targetUrl}
                  onChange={(e) => setTargetUrl(e.target.value)}
                  placeholder="https://…"
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Platform ID</label>
                <input
                  type="text"
                  value={targetId}
                  onChange={(e) => setTargetId(e.target.value)}
                  placeholder="Numeric ID"
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2"
                />
              </div>
            </div>

            {action === "comment" && (
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Comment Text</label>
                <textarea
                  required
                  value={commentText}
                  onChange={(e) => setCommentText(e.target.value)}
                  rows={2}
                  placeholder="Comment text sent from all selected accounts"
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none"
                />
              </div>
            )}

            {/* Delay settings */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Min delay between accounts (sec)
                </label>
                <input
                  type="number" min={1} max={300}
                  value={delayMin}
                  onChange={(e) => setDelayMin(+e.target.value)}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Max delay between accounts (sec)
                </label>
                <input
                  type="number" min={1} max={300}
                  value={delayMax}
                  onChange={(e) => setDelayMax(+e.target.value)}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Schedule (optional)</label>
              <input
                type="datetime-local"
                value={scheduleAt}
                onChange={(e) => setScheduleAt(e.target.value)}
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2"
              />
            </div>

            {/* Account selector */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-medium text-gray-600">
                  Select Accounts ({selectedIds.length}/{filtered.length})
                </label>
                <div className="flex gap-2">
                  <select
                    value={filterPlatform}
                    onChange={(e) => setFilterPlatform(e.target.value)}
                    className="text-xs border border-gray-200 rounded px-2 py-1"
                  >
                    <option value="">All Platforms</option>
                    <option value="soundcloud">SoundCloud</option>
                    <option value="tiktok">TikTok</option>
                    <option value="twitter">Twitter</option>
                    <option value="spotify">Spotify</option>
                  </select>
                  <button
                    type="button"
                    onClick={toggleAll}
                    className="text-xs px-2 py-1 border border-gray-200 rounded hover:bg-gray-50 transition"
                  >
                    {selectedIds.length === filtered.length ? "Deselect All" : "Select All"}
                  </button>
                </div>
              </div>
              <div className="border border-gray-200 rounded-lg max-h-48 overflow-y-auto divide-y divide-gray-50">
                {filtered.map((a) => (
                  <label key={a.id} className="flex items-center gap-3 px-3 py-2 hover:bg-gray-50 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(a.id)}
                      onChange={() => toggle(a.id)}
                      className="rounded"
                    />
                    <span className="text-sm font-medium text-gray-800">{a.username}</span>
                    <span className="text-xs text-gray-400 capitalize ml-auto">{a.platform}</span>
                  </label>
                ))}
                {filtered.length === 0 && (
                  <p className="text-sm text-gray-400 text-center py-4">No accounts</p>
                )}
              </div>
            </div>
          </div>

          <div className="px-5 py-4 border-t border-gray-100 flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={bulk.isPending || !selectedIds.length}
              className="flex-1 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition flex items-center justify-center gap-1.5 disabled:opacity-60"
            >
              <Zap size={13} />
              {scheduleAt ? `Schedule for ${selectedIds.length} accounts` : `Run on ${selectedIds.length} accounts`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
