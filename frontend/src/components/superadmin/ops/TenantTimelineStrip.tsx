import React from 'react';

interface TimelineEvent {
  ts: string;
  category: string;
  severity: string;
  status: string;
  message: string;
}

interface TenantTimelineStripProps {
  loading?: boolean;
  tenantName?: string;
  events: TimelineEvent[];
}

export const TenantTimelineStrip: React.FC<TenantTimelineStripProps> = ({ loading = false, tenantName, events }) => {
  return (
    <section className="rounded-xl border border-gray-200 bg-white">
      <div className="border-b border-gray-100 px-4 py-3">
        <h3 className="text-sm font-semibold text-gray-900">Tenant Timeline</h3>
        <p className="mt-1 text-xs text-gray-500">
          Correlated tenant events, replay runs, and operational signals{tenantName ? ` for ${tenantName}` : ''}.
        </p>
      </div>
      <div className="max-h-56 overflow-y-auto px-4 py-3">
        {loading ? (
          <div className="text-sm text-gray-500">Loading timeline...</div>
        ) : events.length === 0 ? (
          <div className="text-sm text-gray-500">No timeline events for selected window.</div>
        ) : (
          <div className="space-y-2">
            {events.slice(0, 50).map((event, index) => (
              <div key={`${event.ts}-${index}`} className="rounded-lg border border-gray-100 px-3 py-2 text-xs">
                <div className="font-medium text-gray-800">
                  {event.category} • {event.status}
                </div>
                <div className="mt-1 text-gray-500">
                  {new Date(event.ts).toLocaleString()} • {event.severity}
                </div>
                {event.message && <div className="mt-1 text-gray-700">{event.message}</div>}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
};

