import { useEffect, useRef, useState } from "react";

export interface MultiSelectOption {
  value: string;
  label: string;
  sub?: string;
}

export function MultiSelect({
  options,
  selected,
  onChange,
  placeholder = "Select…",
  disabled = false,
}: {
  options: MultiSelectOption[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function toggle(v: string) {
    const next = new Set(selected);
    if (next.has(v)) next.delete(v); else next.add(v);
    onChange(next);
  }

  const selectedOptions = options.filter((o) => selected.has(o.value));
  const summary =
    selected.size === 0
      ? placeholder
      : selectedOptions.map((o) => o.label).join(", ");

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() => !disabled && setOpen(!open)}
        disabled={disabled}
        style={{
          width: "100%",
          textAlign: "left",
          padding: "8px 12px",
          fontSize: 13,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          opacity: summary === placeholder ? 0.6 : 1,
        }}
      >
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {selected.size > 0 && (
            <span className="badge badge-ok" style={{ marginRight: 6, fontSize: 11 }}>
              {selected.size}
            </span>
          )}
          {summary}
        </span>
        <span style={{ fontSize: 10, marginLeft: 8 }}>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            zIndex: 100,
            background: "var(--bg-elev)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            maxHeight: 320,
            overflow: "auto",
            boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
          }}
        >
          <div style={{ padding: "4px 8px", borderBottom: "1px solid var(--border)", fontSize: 11 }}>
            <button
              type="button"
              onClick={() => onChange(new Set(options.map((o) => o.value)))}
              style={{ fontSize: 11, padding: "2px 6px", marginRight: 6 }}
            >
              All
            </button>
            <button
              type="button"
              onClick={() => onChange(new Set())}
              style={{ fontSize: 11, padding: "2px 6px" }}
            >
              None
            </button>
          </div>
          {options.map((o) => (
            <label
              key={o.value}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 10px",
                cursor: "pointer",
                fontSize: 13,
                borderBottom: "1px solid var(--bg-elev-2)",
              }}
            >
              <input
                type="checkbox"
                checked={selected.has(o.value)}
                onChange={() => toggle(o.value)}
              />
              <div>
                <div>{o.label}</div>
                {o.sub && (
                  <div className="dim mono" style={{ fontSize: 11 }}>{o.sub}</div>
                )}
              </div>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
