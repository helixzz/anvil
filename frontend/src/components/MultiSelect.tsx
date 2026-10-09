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
  searchPlaceholder = "Filter…",
  allLabel = "All",
  noneLabel = "None",
}: {
  options: MultiSelectOption[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  placeholder?: string;
  disabled?: boolean;
  searchPlaceholder?: string;
  allLabel?: string;
  noneLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
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

  // Every whitespace-separated term must match, so "cobalt003 memblaze"
  // narrows to one model on one host; All/None then act on that subset.
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  const visible = terms.length
    ? options.filter((o) => {
        const hay = `${o.label} ${o.sub ?? ""}`.toLowerCase();
        return terms.every((term) => hay.includes(term));
      })
    : options;

  function setVisible(on: boolean) {
    const next = new Set(selected);
    for (const o of visible) {
      if (on) next.add(o.value); else next.delete(o.value);
    }
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
            maxHeight: 420,
            overflow: "auto",
            boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
          }}
        >
          <div
            style={{
              position: "sticky",
              top: 0,
              zIndex: 1,
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "6px 8px",
              background: "var(--bg-elev)",
              borderBottom: "1px solid var(--border)",
              fontSize: 11,
            }}
          >
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={searchPlaceholder}
              style={{ flex: 1, fontSize: 12, padding: "3px 8px" }}
            />
            <button
              type="button"
              onClick={() => setVisible(true)}
              style={{ fontSize: 11, padding: "2px 6px" }}
            >
              {allLabel}
            </button>
            <button
              type="button"
              onClick={() => setVisible(false)}
              style={{ fontSize: 11, padding: "2px 6px" }}
            >
              {noneLabel}
            </button>
            <span className="dim">{visible.length}/{options.length}</span>
          </div>
          {visible.map((o) => (
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
