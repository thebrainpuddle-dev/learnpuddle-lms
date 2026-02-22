import React from 'react';
import type { TeacherCalendarDay, TeacherCalendarEvent } from '../../../services/teacherService';

interface TeacherCalendarFiveDayProps {
  days: TeacherCalendarDay[];
  events: TeacherCalendarEvent[];
  onOpenEvent: (event: TeacherCalendarEvent) => void;
}

const colorClass: Record<TeacherCalendarEvent['color'], string> = {
  amber: 'from-orange-400 to-orange-300 text-orange-950',
  rose: 'from-rose-300 to-rose-200 text-rose-950',
  sky: 'from-sky-400 to-sky-300 text-sky-950',
};

function parseMinutes(label: string) {
  const [hh, mm] = label.split(':').map((part) => Number(part));
  if (!Number.isFinite(hh) || !Number.isFinite(mm)) return 0;
  return hh * 60 + mm;
}

export const TeacherCalendarFiveDay: React.FC<TeacherCalendarFiveDayProps> = ({
  days,
  events,
  onOpenEvent,
}) => {
  const [selectedDate, setSelectedDate] = React.useState(() => {
    const today = days.find((day) => day.is_today);
    return today?.date || days[0]?.date || '';
  });
  const selectedIndex = Math.max(
    0,
    days.findIndex((day) => day.date === selectedDate),
  );
  const selectedDay = days[selectedIndex];
  const selectedEvents = events.filter((event) => event.date === selectedDate);

  React.useEffect(() => {
    if (!days.length) {
      setSelectedDate('');
      return;
    }
    if (selectedDate && days.some((day) => day.date === selectedDate)) {
      return;
    }
    const today = days.find((day) => day.is_today);
    setSelectedDate(today?.date || days[0].date);
  }, [days, selectedDate]);

  const showDay = (index: number) => {
    const day = days[index];
    if (day) setSelectedDate(day.date);
  };

  const startMinutes = 7 * 60;
  const endMinutes = 20 * 60;
  const totalMinutes = endMinutes - startMinutes;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-4 flex items-center justify-between gap-2">
        <h3 className="text-lg font-semibold text-slate-900">5-Day Planner</h3>
        <p className="text-sm font-semibold text-indigo-600">
          {(selectedDay?.total_minutes || 0) > 0
            ? `${Math.round((selectedDay.total_minutes / 60) * 10) / 10}h planned`
            : 'No tasks'}
        </p>
      </div>

      <div className="mb-4 flex items-center gap-2">
        <button
          type="button"
          onClick={() => showDay(selectedIndex - 1)}
          disabled={selectedIndex <= 0}
          className="h-9 w-9 rounded-full border border-indigo-200 text-indigo-700 disabled:opacity-30"
          aria-label="Previous day"
        >
          ←
        </button>
        <div className="grid flex-1 grid-cols-5 gap-2">
          {days.map((day) => (
            <button
              type="button"
              key={day.date}
              onClick={() => setSelectedDate(day.date)}
              className={`rounded-xl border p-2 text-left transition ${
                selectedDate === day.date
                  ? 'border-indigo-500 bg-indigo-600 text-white'
                  : 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100'
              }`}
            >
              <p className="text-xl font-semibold leading-none">{day.day}</p>
              <p className="text-xs">{day.short_weekday}</p>
              <p className="mt-1 text-xs font-semibold">{day.task_count} tasks</p>
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => showDay(selectedIndex + 1)}
          disabled={selectedIndex >= days.length - 1}
          className="h-9 w-9 rounded-full border border-indigo-200 text-indigo-700 disabled:opacity-30"
          aria-label="Next day"
        >
          →
        </button>
      </div>

      <div className="overflow-x-auto">
        <div className="relative min-w-[760px] rounded-xl border border-slate-200 bg-slate-50 p-3">
          <div className="mb-2 grid grid-cols-14 text-xs font-medium text-slate-400">
            {Array.from({ length: 14 }).map((_, idx) => (
              <span key={idx}>{`${(7 + idx).toString().padStart(2, '0')}:00`}</span>
            ))}
          </div>
          <div className="relative h-48 rounded-lg bg-white">
            {Array.from({ length: 14 }).map((_, idx) => (
              <div
                key={idx}
                className="absolute top-0 bottom-0 border-l border-slate-100"
                style={{ left: `${(idx / 13) * 100}%` }}
              />
            ))}

            {selectedEvents.map((event) => {
              const eventStart = parseMinutes(event.start_time);
              const eventEnd = parseMinutes(event.end_time);
              const leftPct = ((eventStart - startMinutes) / totalMinutes) * 100;
              const widthPct = Math.max(8, ((eventEnd - eventStart) / totalMinutes) * 100);
              const topOffset = 14 + (eventStart % 120);
              return (
                <button
                  key={event.id}
                  type="button"
                  onClick={() => onOpenEvent(event)}
                  className={`absolute rounded-xl bg-gradient-to-br px-3 py-2 text-left shadow transition hover:scale-[1.01] ${colorClass[event.color]}`}
                  style={{
                    left: `${Math.max(0, leftPct)}%`,
                    width: `${Math.min(100 - Math.max(0, leftPct), widthPct)}%`,
                    top: `${Math.min(120, topOffset)}px`,
                  }}
                >
                  <p className="text-sm font-semibold leading-tight">{event.title}</p>
                  <p className="text-xs opacity-80">{event.subtitle}</p>
                  <p className="mt-1 text-xs font-semibold">
                    {event.start_time} - {event.end_time}
                  </p>
                </button>
              );
            })}

            {selectedEvents.length === 0 && (
              <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-400">
                No scheduled tasks for this day.
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
};
