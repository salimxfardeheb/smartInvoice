"use client";

import {
  forwardRef,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

const FIELD_CLASS =
  "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30 disabled:bg-slate-50 disabled:text-slate-400";

interface FieldWrapperProps {
  label?: string;
  error?: string | null;
  hint?: string;
  children: ReactNode;
}

function FieldWrapper({ label, error, hint, children }: FieldWrapperProps) {
  return (
    <label className="block">
      {label && (
        <span className="mb-1 block text-xs font-medium text-slate-700">{label}</span>
      )}
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-slate-400">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-rose-600">{error}</span>}
    </label>
  );
}

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string | null;
  hint?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, hint, className = "", ...rest },
  ref,
) {
  return (
    <FieldWrapper label={label} error={error} hint={hint}>
      <input ref={ref} className={`${FIELD_CLASS} ${className}`} {...rest} />
    </FieldWrapper>
  );
});

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string | null;
  hint?: string;
  options: Array<{ value: string; label: string }>;
}

export function Select({ label, error, hint, options, className = "", ...rest }: SelectProps) {
  return (
    <FieldWrapper label={label} error={error} hint={hint}>
      <select className={`${FIELD_CLASS} ${className}`} {...rest}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </FieldWrapper>
  );
}

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string | null;
  hint?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, error, hint, className = "", ...rest },
  ref,
) {
  return (
    <FieldWrapper label={label} error={error} hint={hint}>
      <textarea ref={ref} className={`${FIELD_CLASS} ${className}`} {...rest} />
    </FieldWrapper>
  );
});
