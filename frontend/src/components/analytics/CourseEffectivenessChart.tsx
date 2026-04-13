// src/components/analytics/CourseEffectivenessChart.tsx
//
// Scatter-style chart: completion rate vs average score per course.
// Helps identify courses that are too easy or too hard.
// Uses placeholder data — TODO: wire to backend analytics endpoint.

import React, { useMemo } from 'react';
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, Cell,
  ResponsiveContainer, ZAxis,
} from 'recharts';
import { AcademicCapIcon, EyeIcon } from '@heroicons/react/24/outline';

/* ── Types ─────────────────────────────────────────────────────── */

interface CourseEffectivenessItem {
  courseId: string;
  courseName: string;
  completionRate: number; // 0-100
  avgScore: number; // 0-100
  enrolledCount: number;
}

interface CourseEffectivenessChartProps {
  onViewDetails?: () => void;
}

/* ── Placeholder data (TODO: replace with API call) ──────────── */

const MOCK_DATA: CourseEffectivenessItem[] = [
  { courseId: '1', courseName: 'Child Safety Basics', completionRate: 95, avgScore: 88, enrolledCount: 45 },
  { courseId: '2', courseName: 'IB Methods Level 1', completionRate: 70, avgScore: 72, enrolledCount: 38 },
  { courseId: '3', courseName: 'Advanced Pedagogy', completionRate: 40, avgScore: 55, enrolledCount: 30 },
  { courseId: '4', courseName: 'Digital Tools', completionRate: 85, avgScore: 92, enrolledCount: 50 },
  { courseId: '5', courseName: 'Classroom Management', completionRate: 60, avgScore: 65, enrolledCount: 42 },
  { courseId: '6', courseName: 'Special Needs Ed', completionRate: 50, avgScore: 78, enrolledCount: 20 },
  { courseId: '7', courseName: 'Leadership Essentials', completionRate: 30, avgScore: 45, enrolledCount: 15 },
];

/* ── Helpers ───────────────────────────────────────────────────── */

function difficultyColor(completionRate: number, avgScore: number): string {
  // Too easy: high completion + high score
  if (completionRate >= 80 && avgScore >= 80) return '#3b82f6'; // blue
  // Well-balanced
  if (completionRate >= 50 && avgScore >= 50) return '#10b981'; // green
  // Too hard: low completion or low score
  return '#ef4444'; // red
}

/* ── Custom tooltip ───────────────────────────────────────────── */

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  const item = payload[0].payload as CourseEffectivenessItem;
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm px-3 py-2 text-xs">
      <p className="font-medium text-gray-900">{item.courseName}</p>
      <p className="text-gray-600">Completion: {item.completionRate}%</p>
      <p className="text-gray-600">Avg Score: {item.avgScore}%</p>
      <p className="text-gray-600">Enrolled: {item.enrolledCount}</p>
    </div>
  );
};

/* ── Component ─────────────────────────────────────────────────── */

export const CourseEffectivenessChart: React.FC<CourseEffectivenessChartProps> = ({
  onViewDetails,
}) => {
  // TODO: Replace with useQuery call to backend endpoint
  // const { data } = useQuery({ queryKey: ['courseEffectiveness'], queryFn: ... });
  const data = MOCK_DATA;

  const chartData = useMemo(
    () => data.map((d) => ({
      ...d,
      x: d.completionRate,
      y: d.avgScore,
      z: Math.max(60, Math.min(400, d.enrolledCount * 8)),
    })),
    [data]
  );

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <AcademicCapIcon className="h-5 w-5 text-purple-600" />
          <h2 className="font-semibold text-gray-900">Course Effectiveness</h2>
        </div>
        {onViewDetails && (
          <button
            type="button"
            onClick={onViewDetails}
            className="inline-flex items-center gap-1 text-xs font-medium text-primary-600 hover:text-primary-700"
          >
            <EyeIcon className="h-4 w-4" />
            View Details
          </button>
        )}
      </div>

      {/* Legend */}
      <div className="mb-3 flex flex-wrap gap-3 text-xs text-gray-500">
        <div className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-blue-500" /> Easy (high completion + score)</div>
        <div className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-500" /> Balanced</div>
        <div className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-red-500" /> Challenging (low completion or score)</div>
      </div>

      <div className="h-56">
        {data.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.05)" />
              <XAxis
                type="number"
                dataKey="x"
                name="Completion Rate"
                domain={[0, 100]}
                tickFormatter={(v) => `${v}%`}
                label={{ value: 'Completion Rate %', position: 'insideBottom', offset: -5, style: { fontSize: 11 } }}
              />
              <YAxis
                type="number"
                dataKey="y"
                name="Average Score"
                domain={[0, 100]}
                tickFormatter={(v) => `${v}%`}
                label={{ value: 'Average Score %', angle: -90, position: 'insideLeft', style: { fontSize: 11 } }}
              />
              <ZAxis type="number" dataKey="z" range={[60, 400]} />
              <Tooltip content={<CustomTooltip />} />
              <Scatter data={chartData}>
                {chartData.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={difficultyColor(entry.completionRate, entry.avgScore)}
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            No course data yet
          </div>
        )}
      </div>
    </div>
  );
};
