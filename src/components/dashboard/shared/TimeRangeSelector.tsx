import React from 'react';

interface TimeRangeSelectorProps {
  value: string;
  onChange: (value: string) => void;
  options: string[];
  label?: string;
  className?: string;
}

export const TimeRangeSelector: React.FC<TimeRangeSelectorProps> = ({
  value,
  onChange,
  options,
  label,
  className = ''
}) => {
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onChange(e.target.value);
  };

  return (
    <div className={`inline-flex items-center gap-2 ${className}`}>
      {label && (
        <label className="text-sm text-slate-400">
          {label}
        </label>
      )}
      <div className="relative">
        <select
          value={value}
          onChange={handleChange}
          className="
            appearance-none
            bg-slate-800
            text-slate-200
            text-sm
            font-medium
            px-3 py-1.5
            pr-8
            rounded-md
            border border-slate-700
            hover:border-slate-600
            focus:outline-none
            focus:ring-2
            focus:ring-blue-500/50
            focus:border-blue-500
            cursor-pointer
            transition-colors
          "
        >
          {options.map((option) => (
            <option
              key={option}
              value={option}
              className="bg-slate-800 text-slate-200"
            >
              {option}
            </option>
          ))}
        </select>
        {/* Dropdown arrow */}
        <div className="absolute inset-y-0 right-0 flex items-center pr-2 pointer-events-none">
          <svg
            className="w-4 h-4 text-slate-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 9l-7 7-7-7"
            />
          </svg>
        </div>
      </div>
    </div>
  );
};

export default TimeRangeSelector;
