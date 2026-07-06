import { createFileRoute, Navigate } from "@tanstack/react-router";

export const Route = createFileRoute("/birth-data")({
  head: () => ({ meta: [{ title: "Birth Data — JyotishAI" }] }),
  component: () => <Navigate to="/" replace />,
});
