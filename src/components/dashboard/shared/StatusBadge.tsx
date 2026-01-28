import React from 'react';

interface StatusBadgeProps {
  status: 'healthy' | 'caution' | 'critical';
}

const statusConfig = {
  healthy: {
    label: 'Healthy',
    bgColor: 'bg-emerald-500/20',
    textColor: 'text-emerald-400',
    dotColor: 'bg-emerald-500',
    borderColor: 'border-emerald-500/30'
  },
  caution: {
    label: 'Caution',
    bgColor: 'bg-amber-500/20',
    textColor: 'text-amber-400',
    dotColor: 'bg-amber-500',
    borderColor: 'border-amber-500/30'
  },
  critical: {
    label: 'Critical',
    bgColor: 'bg-red-500/20',
    textColor: 'text-red-400',
    dotColor: 'bg-red-500',
    borderColor: 'border-red-500/30'
  }
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const config = statusConfig[status];

  return (
    <span
      className={`
        inline-flex items-center gap-1.5 px-2.5 py-1
        rounded-full text-xs font-medium
        ${config.bgColor} ${config.textColor}
        border ${config.borderColor}
      `}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${config.dotColor}`}
        aria-hidden="true"
      />
      {config.label}
    </span>
  );
};

export default StatusBadge;
