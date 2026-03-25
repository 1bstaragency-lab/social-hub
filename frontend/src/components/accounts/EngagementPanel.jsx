/**
 * EngagementPanel — modal for firing engagement actions on one account.
 * Actions: like, unlike, repost, unrepost, comment, follow, unfollow, play, save, add_to_playlist
 */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { engagementApi } from "../../services/api";
import { X, Zap, Clock } from "lucide-react";
import toast from "react-hot-toast";

const ACTIONS = [
  { value: "like",            label: "❤️  Like" },
  { value: "unlike",          label: "💔  Unlike" },
  { value: "repost",          label: "🔁  Repost" },
  { value: "unrepost",        label: "↩️  Unrepost" },
  { value: "comment",         label: "💬  Comment" },
  { value: "follow",          label: "➕  Follow" },
  { value: "unfollow",        label: "➖  Unfollow" },
  { value: "play",            label: "▶️  Play Track" },
  { value: "save",            label: "🔖  Save Track" },
  { value: "add_to_playlist", label: "📋  Add to Playlist" },
];

export default function EngagementPanel({ account, defaultAction = "like", onClose }) {
  const [action, setAction] = useState(defaultAction);
  const [targetUrl, setTargetUrl] = useState("");
  const [targetId, setTargetId] = useState("");
  const [commentText, setCommentText] = useState("");
  const [playlistId, setPlaylistId] = useState("");
  const [scheduleAt, setScheduleAt] = useState("");

  const qc = useQueryClient();

  const fire = useMutation({
    mutationFn: (data) => engagementApi.action(data),
    onSuccess: (r) => {
      const d = r.data;
      if (d.status === "scheduled") {
        toast.success(`Action scheduled for ${new Date(d.scheduled_at).toLocaleString()}`);
      } else {
        toast.success(`${action} dispatched — Task ID: ${d.task_id?.slice(0, 8)}…`);
      }
      onClose();
    },
    onError: (err) => toast.error(err.response?.data?.detail || "Action failed"),
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    fire.mutate({
      account_id: account.id,
      action_type: action,
      target_url: targetUrl || undefined,
      target_platform_id: targetId || undefined,
      comment_text: commentText || undefined,
      playlist_id: playlistId || undefined,
      scheduled_at: scheduleAt ? new Date(scheduleAt).toISOString() : undefined,
    });
  };

  const needsComment = action === "comment";
  const needsPlaylist = action === "add_to_playlist";

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div>
            <h2 className="font-semibold text-gray-900">Engagement Action</h2>
            <p className="text-xs text-gray-400">@{account.username} · {account.platform}</p>
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-100 rounded-lg transition">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {/* Action selector */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">Action</label>
            <div className="grid grid-cols-2 gap-1.5">
              {ACTIONS.map((a) => (
                <button
                  key={a.value}
                  type="button"
                  onClick={() => setAction(a.value)}
                  className={`text-left text-sm px-3 py-2 rounded-lg border transition ${
                    action === a.value
                      ? "border-indigo-500 bg-indigo-50 text-indigo-700 font-medium"
                      : "border-gray-200 hover:border-gray-300"
                  }`}
                >
                  {a.label}
                </button>
              ))}
            </div>
          </div>

          {/* Target */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Target URL <span className="text-gray-400">(paste the link)</span>
            </label>
            <input
              type="url"
              value={targetUrl}
              onChange={(e) => setTargetUrl(e.target.value)}
              placeholder="https://soundcloud.com/artist/track-name"
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Platform ID <span className="text-gray-400">(optional, numeric ID)</span>
            </label>
            <input
              type="text"
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
              placeholder="1234567890"
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
          </div>

          {needsComment && (
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Comment Text</label>
              <textarea
                required
                value={commentText}
                onChange={(e) => setCommentText(e.target.value)}
                rows={3}
                placeholder="Write your comment…"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400 resize-none"
              />
            </div>
          )}

          {needsPlaylist && (
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Playlist ID</label>
              <input
                type="text"
                required
                value={playlistId}
                onChange={(e) => setPlaylistId(e.target.value)}
                placeholder="Playlist ID or URL"
                className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
            </div>
          )}

          {/* Optional schedule */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1 flex items-center gap-1">
              <Clock size={11} /> Schedule for later <span className="text-gray-400">(optional)</span>
            </label>
            <input
              type="datetime-local"
              value={scheduleAt}
              onChange={(e) => setScheduleAt(e.target.value)}
              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            />
          </div>

          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={fire.isPending}
              className="flex-1 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition flex items-center justify-center gap-1.5 disabled:opacity-60"
            >
              <Zap size={13} />
              {scheduleAt ? "Schedule" : "Run Now"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
