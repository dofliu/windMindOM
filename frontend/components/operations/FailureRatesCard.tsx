/**
 * 故障率回饋（WMOM-20261127-07，DEC-20261127-09）：本風場由工單修好的故障，依 K13 元件和參考故障率對照。
 *
 * 回饋後的故障率＝（K13 × 先驗機組年＋修過的次數）÷（先驗機組年＋運轉機組年）。只列模擬器會讓它壞的元件；
 * 拿回饋後的故障率跑成本試算用 `POST /api/cost/monte-carlo/empirical`。
 */

import React, { useEffect, useState } from "react";
import { Card } from "../ui";
import { useTheme } from "../../theme/ThemeProvider";
import {
  fetchFailureRates,
  type FailureRatesResponse,
} from "../../services/operationsService";
import {
  explainError,
  fmtPct,
  pick,
  useTableStyles,
  type Lang,
} from "./shared";

function fmtRate(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "—";
  return value.toFixed(3);
}

interface Props {
  lang: Lang;
}

const FailureRatesCard: React.FC<Props> = ({ lang }) => {
  const { C } = useTheme();
  const ui = pick(lang);
  const { th, num, thNum, td } = useTableStyles();
  const [data, setData] = useState<FailureRatesResponse | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let alive = true;
    fetchFailureRates()
      .then((body) => alive && setData(body))
      .catch((e) => alive && setError(e));
    return () => {
      alive = false;
    };
  }, []);

  // 輔助的一張表：讀不到時只留一行小字，不搶收支本身的錯誤提示
  if (error) {
    return (
      <div style={{ fontSize: 12, color: C.faint }}>
        {ui("Failure-rate feedback unavailable: ", "故障率回饋讀不到：")}
        {explainError(error, lang)}
      </div>
    );
  }
  if (!data) return null;
  const rows = data.components.filter((row) => row.modelled);
  const unmapped = Object.entries(data.unmapped);
  return (
    <div data-testid="failure-rates">
      <Card padding={0}>
        <div style={{ padding: "16px 16px 8px", display: "grid", gap: 4 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: C.text }}>
            {ui(
              "Failure rates fed back from this farm",
              "故障率回饋：本風場的維修紀錄 vs K13",
            )}
          </div>
          <div style={{ fontSize: 12, color: C.sub }}>
            {ui(
              `${data.turbine_years.toFixed(2)} turbine-years of operation; the K13 rate counts as ${data.prior_turbine_years} turbine-years of experience. Rates are failures per turbine per year.`,
              `運轉 ${data.turbine_years.toFixed(2)} 機組年；K13 的故障率算 ${data.prior_turbine_years} 機組年的經驗。故障率是每台機組每年幾次。`,
            )}
          </div>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table
            style={{ width: "100%", borderCollapse: "collapse" }}
            aria-label={ui("Failure rates", "故障率回饋")}
          >
            <thead>
              <tr>
                <th style={th}>{ui("K13 component", "K13 元件")}</th>
                <th style={thNum}>{ui("K13 rate", "K13 故障率")}</th>
                <th style={thNum}>{ui("Repairs", "修過")}</th>
                <th style={thNum}>{ui("This farm only", "只看本風場")}</th>
                <th style={thNum}>{ui("Fed back", "回饋後")}</th>
                <th style={thNum}>{ui("Weight of this farm", "本風場比重")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.code}>
                  <td style={td}>{row.name}</td>
                  <td style={num}>{fmtRate(row.k13_rate)}</td>
                  <td style={num}>{row.repairs}</td>
                  <td style={num}>{fmtRate(row.observed_rate)}</td>
                  <td
                    style={{
                      ...num,
                      color: row.rate > row.k13_rate ? C.warn : C.text,
                    }}
                  >
                    {fmtRate(row.rate)}
                  </td>
                  <td style={num}>{fmtPct(row.weight)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {unmapped.length > 0 && (
          <div
            style={{ padding: "8px 16px 14px", fontSize: 12, color: C.faint }}
          >
            {ui(
              "Not counted (not a component failure): ",
              "不算進故障率（不是元件故障）：",
            )}
            {unmapped.map(([sid, n]) => `${sid} × ${n}`).join("、")}
          </div>
        )}
      </Card>
    </div>
  );
};

export default FailureRatesCard;
