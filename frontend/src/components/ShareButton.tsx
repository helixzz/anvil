import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "@/api";

export function ShareButton({ runId }: { runId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [copied, setCopied] = useState(false);
  const shareQ = useQuery({
    queryKey: ["run-share", runId],
    queryFn: () => api.getRunShare(runId),
  });
  const createMut = useMutation({
    mutationFn: () => api.createRunShare(runId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["run-share", runId] }),
  });
  const revokeMut = useMutation({
    mutationFn: () => api.revokeRunShare(runId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["run-share", runId] }),
  });

  const slug = shareQ.data?.share_slug;
  const publicUrl = slug
    ? `${window.location.origin}/r/runs/${slug}`
    : null;

  async function copy() {
    if (!publicUrl) return;
    try {
      await navigator.clipboard.writeText(publicUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API unavailable (non-HTTPS origins, older browsers);
      // fall back to a prompt so the user can still copy manually.
      window.prompt(t("runs.shareCopyFallback"), publicUrl);
    }
  }

  if (!slug) {
    return (
      <button
        onClick={() => createMut.mutate()}
        disabled={createMut.isPending}
        title={t("runs.shareHelp")}
      >
        {createMut.isPending ? t("common.loading") : t("runs.shareCreate")}
      </button>
    );
  }

  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
      <input
        type="text"
        readOnly
        value={publicUrl ?? ""}
        style={{ width: 280, fontFamily: "ui-monospace, monospace", fontSize: 11 }}
        onFocus={(e) => e.currentTarget.select()}
      />
      <button onClick={copy}>
        {copied ? t("runs.shareCopied") : t("runs.shareCopy")}
      </button>
      <button
        onClick={() => {
          if (window.confirm(t("runs.shareRevokeConfirm"))) revokeMut.mutate();
        }}
        disabled={revokeMut.isPending}
        className="btn-danger"
      >
        {t("runs.shareRevoke")}
      </button>
    </div>
  );
}
