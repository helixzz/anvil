import { useTranslation } from "react-i18next";

export interface PcieLinkData {
  address?: string;
  capability?: {
    raw?: string | null;
    speed_gt?: number | null;
    width?: number | null;
    pcie_gen?: string | null;
  } | null;
  status?: {
    raw?: string | null;
    speed_gt?: number | null;
    width?: number | null;
    pcie_gen?: string | null;
  } | null;
  degraded?: boolean;
  speed_degraded?: boolean;
  width_degraded?: boolean;
}

function fmtLink(
  gen: string | null | undefined,
  speed_gt: number | null | undefined,
  width: number | null | undefined,
): string {
  const parts: string[] = [];
  if (gen) parts.push(gen);
  if (speed_gt != null) parts.push(`${speed_gt} GT/s`);
  if (width != null) parts.push(`x${width}`);
  return parts.length ? parts.join(" · ") : "—";
}

export function PcieLinkCard({
  title,
  pcie,
}: {
  title?: string;
  pcie: PcieLinkData | null | undefined;
}) {
  const { t } = useTranslation();
  if (!pcie || (!pcie.capability && !pcie.status)) return null;
  const cap = pcie.capability || {};
  const st = pcie.status || {};
  const badgeClass = pcie.degraded ? "badge-warn" : "badge-ok";
  const verdict = pcie.degraded ? t("pcie.degraded") : t("pcie.optimal");

  return (
    <div className="card">
      <div
        className="row"
        style={{ justifyContent: "space-between", alignItems: "baseline" }}
      >
        <h3 style={{ margin: 0 }}>{title ?? t("pcie.title")}</h3>
        <span className={`badge ${badgeClass}`}>{verdict}</span>
      </div>
      <div className="dim" style={{ fontSize: 11, marginTop: 6 }}>
        {t("pcie.help")}
      </div>
      <table style={{ marginTop: 12 }}>
        <thead>
          <tr>
            <th>{t("pcie.column")}</th>
            <th>{t("pcie.link")}</th>
            <th>{t("pcie.raw")}</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td className="mono">{t("pcie.capability")}</td>
            <td className="mono">
              {fmtLink(cap.pcie_gen, cap.speed_gt, cap.width)}
            </td>
            <td className="mono dim" style={{ fontSize: 11 }}>
              {cap.raw ?? "—"}
            </td>
          </tr>
          <tr>
            <td className="mono">{t("pcie.status")}</td>
            <td
              className="mono"
              style={pcie.degraded ? { color: "#fde68a" } : undefined}
            >
              {fmtLink(st.pcie_gen, st.speed_gt, st.width)}
              {pcie.speed_degraded && (
                <span
                  className="badge badge-warn"
                  style={{ marginLeft: 8, fontSize: 10 }}
                >
                  {t("pcie.speedDowngraded")}
                </span>
              )}
              {pcie.width_degraded && (
                <span
                  className="badge badge-warn"
                  style={{ marginLeft: 8, fontSize: 10 }}
                >
                  {t("pcie.widthDowngraded")}
                </span>
              )}
            </td>
            <td className="mono dim" style={{ fontSize: 11 }}>
              {st.raw ?? "—"}
            </td>
          </tr>
        </tbody>
      </table>
      {pcie.address && (
        <div className="dim" style={{ fontSize: 11, marginTop: 8 }}>
          {t("pcie.address")}: <span className="mono">{pcie.address}</span>
        </div>
      )}
    </div>
  );
}
