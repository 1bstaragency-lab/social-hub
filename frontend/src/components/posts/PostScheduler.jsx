import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { postsApi, accountsApi, campaignsApi } from "../../services/api";
import { Plus, Send, Clock, Trash2, ExternalLink } from "lucide-react";
import toast from "react-hot-toast";
import { format } from "date-fns";

const STATUS_COLORS = {
  draft:      "bg-gray-100 text-gray-600",
  scheduled:  "bg-blue-100 text-blue-700",
  queued:     "bg-yellow-100 text-yellow-700",
  publishing: "bg-orange-100 text-orange-700",
  published:  "bg-green-100 text-green-700",
  failed:     "bg-red-100 text-red-700",
  cancelled:  "bg-gray-100 text-gray-400",
};

function CreatePostForm({ onCreated }) {
  const [accountId, setAccountId] = useState("");
  const [campaignId, setCampaignId] = useState("");
  const [postType, setPostType] = useState("text");
  const [content, setContent] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [isCrossPost, setIsCrossPost] = useState(false);
  const [crossAccounts, setCrossAccounts] = useState([]);
  const qc = useQueryClient();

  const { data: accounts = [] } = useQuery({
    queryKey: ["accounts-active"],
    queryFn: () => accountsApi.list({ status: "active", limit: 200 }),
    select: (r) => r.data,
  });

  const { data: campaigns = [] } = useQuery({
    queryKey: ["campaigns-all"],
    queryFn: () => campaignsApi.list({ limit: 100 }),
    select: (r) => r.data,
  });

  const createPost = useMutation({
    mutationFn: (data) => isCrossPost ? postsApi.crossPost(data) : postsApi.create(data),
    onSuccess: () => {
      toast.success(isCrossPost ? "Cross-post scheduled!" : "Post created!");
      qc.invalidateQueries(["posts"]);
      setContent(""); setScheduledAt(""); setAccountId(""); setCrossAccounts([]);
      onCreated?.();
    },
    onError: (err) => toast.error(err.response?.data?.detail || "Failed to create post"),
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    const basePayload = {
      post_type: postType,
      content_text: content,
      scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null,
      campaign_id: campaignId || null,
    };

    if (isCrossPost) {
      createPost.mutate(
        crossAccounts.map((aid) => ({ ...basePayload, account_id: aid }))
      );
    } else {
      createPost.mutate({ ...basePayload, account_id: accountId });
    }
  };

  return (
    <form onSubmit={handleSubmit} className="bg-white rounded-xl border border-gray-100 shadow-sm p-5 space-y-4">
      <h3 className="font-semibold text-gray-800 flex items-center gap-2">
        <Plus size={15} /> Create Post
      </h3>

      <div className="flex items-center gap-3">
        <label className="flex items-center gap-1.5 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={isCrossPost}
            onChange={(e) => setIsCrossPost(e.target.checked)}
            className="rounded"
          />
          Cross-post to multiple accounts
        </label>
      </div>

      {isCrossPost ? (
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1.5">
            Select Accounts ({crossAccounts.length} selected)
          </label>
          <div className="border border-gray-200 rounded-lg max-h-32 overflow-y-auto divide-y divide-gray-50">
            {accounts.map((a) => (
              <label key={a.id} className="flex items-center gap-2 px-3 py-1.5 hover:bg-gray-50 cursor-pointer">
                <input
                  type="checkbox"
                  checked={crossAccounts.includes(a.id)}
                  onChange={(e) => {
                    setCrossAccounts(prev =>
                      e.target.checked ? [...prev, a.id] : prev.filter(x => x !== a.id)
                    );
                  }}
                />
                <span className="text-sm">{a.username}</span>
                <span className="text-xs text-gray-400 capitalize ml-auto">{a.platform}</span>
              </label>
            ))}
          </div>
        </div>
      ) : (
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Account</label>
          <select required value={accountId} onChange={(e) => setAccountId(e.target.value)}
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2">
            <option value="">Select account…</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>{a.username} ({a.platform})</option>
            ))}
          </select>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Campaign</label>
          <select value={campaignId} onChange={(e) => setCampaignId(e.target.value)}
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2">
            <option value="">No campaign</option>
            {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Post Type</label>
          <select value={postType} onChange={(e) => setPostType(e.target.value)}
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2">
            <option value="text">Text</option>
            <option value="image">Image</option>
            <option value="video">Video</option>
            <option value="audio">Audio (SoundCloud)</option>
          </select>
        </div>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">Content</label>
        <textarea
          required
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={3}
          placeholder="Write your post content…"
          className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1 flex items-center gap-1">
          <Clock size={11} /> Schedule <span className="text-gray-400">(leave blank = draft)</span>
        </label>
        <input type="datetime-local" value={scheduledAt}
          onChange={(e) => setScheduledAt(e.target.value)}
          className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2" />
      </div>

      <button type="submit" disabled={createPost.isPending}
        className="w-full py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition flex items-center justify-center gap-2 disabled:opacity-60">
        <Send size={13} />
        {scheduledAt ? "Schedule Post" : "Save as Draft"}
      </button>
    </form>
  );
}

export default function PostScheduler() {
  const [filterStatus, setFilterStatus] = useState("");

  const { data: posts = [], isLoading } = useQuery({
    queryKey: ["posts", filterStatus],
    queryFn: () => postsApi.list({ ...(filterStatus && { status: filterStatus }), limit: 100 }),
    select: (r) => r.data,
    refetchInterval: 30_000,
  });

  const qc = useQueryClient();

  const publishNow = useMutation({
    mutationFn: (id) => postsApi.publishNow(id),
    onSuccess: () => { toast.success("Publishing…"); qc.invalidateQueries(["posts"]); },
    onError: () => toast.error("Publish failed"),
  });

  const deletePost = useMutation({
    mutationFn: (id) => postsApi.delete(id),
    onSuccess: () => { toast.success("Post deleted"); qc.invalidateQueries(["posts"]); },
  });

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
      {/* Create form */}
      <div className="xl:col-span-1">
        <CreatePostForm />
      </div>

      {/* Post list */}
      <div className="xl:col-span-2 space-y-4">
        <div className="flex gap-2">
          {["", "draft", "scheduled", "published", "failed"].map((s) => (
            <button key={s}
              onClick={() => setFilterStatus(s)}
              className={`text-xs px-3 py-1.5 rounded-full border capitalize transition ${
                filterStatus === s ? "bg-indigo-600 text-white border-indigo-600" : "border-gray-200 hover:border-gray-300"
              }`}>
              {s || "All"}
            </button>
          ))}
        </div>

        {isLoading ? (
          <p className="text-sm text-gray-400 text-center py-8">Loading posts…</p>
        ) : (
          <div className="space-y-2">
            {posts.map((post) => (
              <div key={post.id} className="bg-white rounded-xl border border-gray-100 shadow-sm p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-800 truncate">{post.content_text || "(no text)"}</p>
                    <div className="flex items-center gap-3 mt-1.5">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[post.status]}`}>
                        {post.status}
                      </span>
                      {post.scheduled_at && (
                        <span className="text-xs text-gray-400 flex items-center gap-1">
                          <Clock size={10} />
                          {format(new Date(post.scheduled_at), "MMM d, h:mm a")}
                        </span>
                      )}
                      {post.platform_post_url && (
                        <a href={post.platform_post_url} target="_blank" rel="noopener noreferrer"
                          className="text-xs text-indigo-500 flex items-center gap-0.5 hover:underline">
                          <ExternalLink size={10} /> View
                        </a>
                      )}
                    </div>
                    {post.status === "published" && (
                      <div className="flex gap-3 mt-1.5 text-xs text-gray-400">
                        <span>❤️ {post.likes_count}</span>
                        <span>💬 {post.comments_count}</span>
                        <span>🔁 {post.shares_count}</span>
                        <span>👁 {post.views_count}</span>
                        <span>▶️ {post.plays_count}</span>
                      </div>
                    )}
                  </div>
                  <div className="flex gap-1.5 shrink-0">
                    {["draft", "scheduled", "failed"].includes(post.status) && (
                      <button
                        onClick={() => publishNow.mutate(post.id)}
                        className="text-xs px-2.5 py-1 bg-green-100 text-green-700 rounded-lg hover:bg-green-200 transition"
                      >
                        Publish Now
                      </button>
                    )}
                    {["draft", "scheduled"].includes(post.status) && (
                      <button
                        onClick={() => deletePost.mutate(post.id)}
                        className="p-1.5 text-red-400 hover:bg-red-50 rounded-lg transition"
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
            {posts.length === 0 && (
              <div className="text-center py-12 text-gray-400 text-sm">No posts found.</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
