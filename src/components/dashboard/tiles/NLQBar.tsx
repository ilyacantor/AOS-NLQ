import React, { useState, useCallback, KeyboardEvent } from 'react';

interface NLQBarProps {
  placeholder?: string;
  persona: string;
  onSubmit: (query: string) => void;
  disabled?: boolean;
}

export const NLQBar: React.FC<NLQBarProps> = ({
  placeholder,
  persona,
  onSubmit,
  disabled = false
}) => {
  const [query, setQuery] = useState('');

  const defaultPlaceholder = `Ask the ${persona}: "Why is margin declining?"`;

  const handleSubmit = useCallback(() => {
    const trimmedQuery = query.trim();
    if (trimmedQuery && !disabled) {
      onSubmit(trimmedQuery);
      setQuery('');
    }
  }, [query, disabled, onSubmit]);

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

  return (
    <div className="w-full">
      <div
        className={`
          flex items-center gap-3 px-4 py-3
          bg-slate-800 rounded-full
          transition-all duration-200
          focus-within:ring-2 focus-within:ring-cyan-500/50
          ${disabled ? 'opacity-60 cursor-not-allowed' : ''}
        `}
      >
        {/* Chat icon */}
        <div className="flex-shrink-0 text-cyan-400">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            className="w-5 h-5"
          >
            <path
              fillRule="evenodd"
              d="M4.848 2.771A49.144 49.144 0 0112 2.25c2.43 0 4.817.178 7.152.52 1.978.292 3.348 2.024 3.348 3.97v6.02c0 1.946-1.37 3.678-3.348 3.97a48.901 48.901 0 01-3.476.383.39.39 0 00-.297.17l-2.755 4.133a.75.75 0 01-1.248 0l-2.755-4.133a.39.39 0 00-.297-.17 48.9 48.9 0 01-3.476-.384c-1.978-.29-3.348-2.024-3.348-3.97V6.741c0-1.946 1.37-3.68 3.348-3.97z"
              clipRule="evenodd"
            />
          </svg>
        </div>

        {/* Input field */}
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || defaultPlaceholder}
          disabled={disabled}
          className={`
            flex-1 bg-transparent
            text-slate-200 placeholder-slate-500
            text-sm outline-none
            disabled:cursor-not-allowed
          `}
        />

        {/* Submit button */}
        <button
          onClick={handleSubmit}
          disabled={disabled || !query.trim()}
          className={`
            flex-shrink-0 p-2 rounded-full
            transition-all duration-200
            ${query.trim() && !disabled
              ? 'bg-cyan-500 text-white hover:bg-cyan-400 cursor-pointer'
              : 'bg-slate-700 text-slate-500 cursor-not-allowed'
            }
          `}
          aria-label="Submit query"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            className="w-4 h-4"
          >
            <path
              d="M3.478 2.405a.75.75 0 00-.926.94l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.405z"
            />
          </svg>
        </button>
      </div>
    </div>
  );
};

export default NLQBar;
