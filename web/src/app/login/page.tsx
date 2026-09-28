import { Suspense } from "react";
import LoginView from "./LoginView";

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="py-16 text-center text-slate-500">Loading…</div>}>
      <LoginView />
    </Suspense>
  );
}
