import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { Profile } from "@/api";
import { formatDuration } from "@/lib/format";

interface Props {
  profiles: Profile[];
  value: string;
  onChange: (name: string) => void;
  disabled?: boolean;
}

export function ProfilePicker({ profiles, value, onChange, disabled }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLLIElement | null)[]>([]);
  const listboxId = useId();

  const selectedIndex = Math.max(
    0,
    profiles.findIndex((p) => p.name === value),
  );
  const selected = profiles[selectedIndex];

  useEffect(() => {
    if (open) setHighlighted(selectedIndex);
  }, [open, selectedIndex]);

  useEffect(() => {
    if (!open) return;
    const onDocPointer = (e: PointerEvent) => {
      if (!rootRef.current) return;
      if (!rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onDocPointer);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("pointerdown", onDocPointer);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const el = itemRefs.current[highlighted];
    if (el) el.scrollIntoView({ block: "nearest" });
  }, [highlighted, open]);

  function commit(index: number) {
    const p = profiles[index];
    if (!p) return;
    onChange(p.name);
    setOpen(false);
    buttonRef.current?.focus();
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (disabled) return;
    if (!open) {
      if (
        e.key === "ArrowDown" ||
        e.key === "ArrowUp" ||
        e.key === "Enter" ||
        e.key === " "
      ) {
        e.preventDefault();
        setOpen(true);
      }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlighted((i) => Math.min(profiles.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlighted((i) => Math.max(0, i - 1));
    } else if (e.key === "Home") {
      e.preventDefault();
      setHighlighted(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setHighlighted(profiles.length - 1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      commit(highlighted);
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  }

  if (profiles.length === 0) {
    return (
      <button className="profile-picker-trigger" disabled>
        —
      </button>
    );
  }

  return (
    <div className="profile-picker" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className="profile-picker-trigger"
        onClick={() => !disabled && setOpen((v) => !v)}
        onKeyDown={onKeyDown}
        disabled={disabled}
        role="combobox"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={listboxId}
      >
        <span className="profile-picker-trigger-body">
          <span className="profile-picker-row">
            <span className="profile-picker-title">
              {selected?.title ?? t("common.unknown")}
            </span>
            {selected?.destructive ? (
              <span className="badge badge-err profile-picker-flag">
                {t("newRun.destructiveFlag")}
              </span>
            ) : (
              <span className="badge badge-ok profile-picker-flag">
                {t("newRun.nonDestructiveFlag")}
              </span>
            )}
            {selected && (
              <span className="dim profile-picker-meta">
                {formatDuration(selected.estimated_duration_seconds)} ·{" "}
                {selected.phases.length}&nbsp;{t("newRun.phasesUnit")}
              </span>
            )}
          </span>
          <span className="dim profile-picker-desc-one-line">
            {selected?.description}
          </span>
        </span>
        <span className="profile-picker-caret" aria-hidden>
          ▾
        </span>
      </button>

      {open && (
        <ul
          id={listboxId}
          className="profile-picker-listbox"
          role="listbox"
          aria-activedescendant={`${listboxId}-opt-${highlighted}`}
        >
          {profiles.map((p, idx) => {
            const isSelected = p.name === value;
            const isHighlighted = idx === highlighted;
            return (
              <li
                key={p.name}
                id={`${listboxId}-opt-${idx}`}
                ref={(el) => {
                  itemRefs.current[idx] = el;
                }}
                role="option"
                aria-selected={isSelected}
                className={
                  "profile-picker-option" +
                  (isHighlighted ? " highlighted" : "") +
                  (isSelected ? " selected" : "")
                }
                onPointerEnter={() => setHighlighted(idx)}
                onClick={() => commit(idx)}
              >
                <div className="profile-picker-option-head">
                  <span className="profile-picker-title">{p.title}</span>
                  {p.destructive ? (
                    <span className="badge badge-err profile-picker-flag">
                      {t("newRun.destructiveFlag")}
                    </span>
                  ) : (
                    <span className="badge badge-ok profile-picker-flag">
                      {t("newRun.nonDestructiveFlag")}
                    </span>
                  )}
                  <span className="dim profile-picker-meta">
                    {formatDuration(p.estimated_duration_seconds)} ·{" "}
                    {p.phases.length}&nbsp;{t("newRun.phasesUnit")}
                  </span>
                </div>
                <div className="dim profile-picker-desc">{p.description}</div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
