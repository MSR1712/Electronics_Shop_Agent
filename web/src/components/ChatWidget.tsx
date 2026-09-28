"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api";
import { useSession } from "@/context/SessionContext";
import { useVoiceCall } from "@/hooks/useVoiceCall";

type ChatMessage = {
  role: "user" | "assistant";
  text: string;
  escalated?: boolean;
  voice?: boolean;
};

// Talks to POST /api/chat using the SAME session cookie (customer_id +
// conversation_id) the manual checkout pages use — see
// context/SessionContext.tsx. That's what makes "buy 2 via chat" and "buy 2
// via the product page" land in one conversation/customer identity instead
// of two disconnected ones, and it's why an order placed here shows up
// identically at /orders/[id].
export default function ChatWidget() {
  const pathname = usePathname();
  const { session, loading } = useSession();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { status: voiceStatus, start: startVoice, stop: stopVoice } = useVoiceCall({
    onTranscript: ({ role, text }) => setMessages((prev) => [...prev, { role, text, voice: true }]),
    onError: (message) => setVoiceError(message),
  });

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, open]);

  useEffect(() => stopVoice, [stopVoice]); // hang up if the widget unmounts mid-call

  function toggleVoice() {
    setVoiceError(null);
    if (voiceStatus === "idle" || voiceStatus === "error") void startVoice();
    else stopVoice();
  }

  async function send() {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text }]);
    setSending(true);
    try {
      const res = await api.chat(text);
      setMessages((prev) => [...prev, { role: "assistant", text: res.reply, escalated: res.escalated }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "Sorry, something went wrong reaching support. Please try again." },
      ]);
    } finally {
      setSending(false);
    }
  }

  // Customer support chat doesn't belong on the admin panel.
  if (pathname?.startsWith("/admin")) return null;

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col items-end">
      {open && (
        <div className="mb-3 flex h-[28rem] w-80 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl sm:w-96">
          <div className="flex items-center justify-between bg-slate-900 px-4 py-3 text-white">
            <span className="font-semibold">CircuitWorks Support</span>
            <div className="flex items-center gap-1">
              <button
                onClick={toggleVoice}
                disabled={!session || voiceStatus === "connecting"}
                aria-label={voiceStatus === "active" ? "Hang up voice call" : "Start voice call"}
                title={voiceStatus === "active" ? "Hang up" : "Start voice call"}
                className={`rounded-full p-1.5 text-lg hover:bg-white/10 disabled:opacity-40 ${
                  voiceStatus === "active" ? "text-red-400" : "text-slate-300"
                }`}
              >
                {voiceStatus === "active" ? "🔴" : voiceStatus === "connecting" ? "…" : "🎙️"}
              </button>
              <button onClick={() => setOpen(false)} aria-label="Close chat" className="text-slate-300 hover:text-white">
                ✕
              </button>
            </div>
          </div>

          {voiceStatus === "active" && (
            <div className="border-b border-red-100 bg-red-50 px-4 py-2 text-xs font-medium text-red-700">
              🔴 Live voice call — speak any time, no need to press anything.
            </div>
          )}
          {voiceError && (
            <div className="border-b border-amber-100 bg-amber-50 px-4 py-2 text-xs text-amber-800">{voiceError}</div>
          )}

          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
            {!loading && !session && (
              <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-800">
                <Link href="/login?redirect=/" className="font-medium underline">
                  Log in
                </Link>{" "}
                to chat with support and place orders.
              </p>
            )}

            {messages.length === 0 && session && (
              <p className="text-sm text-slate-500">
                Ask about a product, place an order, or ask about our policies.
              </p>
            )}

            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
                    m.role === "user"
                      ? "bg-blue-600 text-white"
                      : m.escalated
                        ? "bg-amber-50 text-amber-900 border border-amber-200"
                        : "bg-slate-100 text-slate-900"
                  }`}
                >
                  {m.escalated && <p className="mb-1 text-xs font-semibold uppercase tracking-wide">Connecting you to a human agent</p>}
                  {m.voice && <span className="mr-1" title="Said over voice">🎙️</span>}
                  {m.text}
                </div>
              </div>
            ))}

            {sending && <div className="text-sm text-slate-400">Thinking…</div>}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
            className="flex items-center gap-2 border-t border-slate-200 p-3"
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={!session || sending || voiceStatus === "active"}
              placeholder={!session ? "Log in to chat" : voiceStatus === "active" ? "Voice call in progress…" : "Type a message…"}
              className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none disabled:bg-slate-50"
            />
            <button
              type="submit"
              disabled={!session || sending || voiceStatus === "active" || !input.trim()}
              className="rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-50"
            >
              Send
            </button>
          </form>
        </div>
      )}

      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Toggle support chat"
        className="flex h-14 w-14 items-center justify-center rounded-full bg-blue-600 text-2xl text-white shadow-lg hover:bg-blue-500"
      >
        {open ? "✕" : "💬"}
      </button>
    </div>
  );
}
